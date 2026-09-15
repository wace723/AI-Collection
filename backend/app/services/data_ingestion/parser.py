"""CSV 解析与入库服务。

职责：
1. 列校验（缺失必填列报 400）
2. 行解析：中文列名 → 模型属性，空字符串 → None，类型转换
3. 入库：按 service_fee_order_no 去重（已存在则跳过），orders + order_features 1:1

不在此处处理鉴权与文件类型校验（属 API 边界，api/data.py 负责）。
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.order import Order, OrderFeature
from app.services.data_ingestion.columns import (
    EXPECTED_COLUMNS,
    EXTRA_FEATURE_COLUMNS,
    FEATURE_FIELD_MAP,
    ORDER_FIELD_MAP,
    REQUIRED_COLUMNS,
    _is_bigint_field,
    _is_bool_field,
    _is_float_field,
    _is_int_field,
)
from app.services.data_ingestion.encoding import EncodingError, detect_and_decode


class CSVParseError(ValueError):
    """CSV 内容或结构错误，对应 400。"""


@dataclass(frozen=True)
class UploadResult:
    """上传结果统计。"""

    inserted: int = 0
    skipped: int = 0
    updated: int = 0  # 重复订单更新支付状态数
    errors: list[str] = field(default_factory=list)


def _check_columns(header: list[str]) -> None:
    """校验表头：必填列必须齐全。缺失则抛 CSVParseError 含缺失列名。"""
    header_set = {h.strip() for h in header}
    missing = [c for c in REQUIRED_COLUMNS if c not in header_set]
    if missing:
        raise CSVParseError(f"缺失必填列: {', '.join(missing)}")


def _empty_to_none(value: str) -> str | None:
    """空字符串（含纯空白）→ None，否则去首尾空白。"""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))  # 容忍 "7.0" 这类写法
    except (ValueError, TypeError):
        return None


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value in {"1", "true", "True", "是"}


def _parse_win_bid_date(value: str | None) -> date | None:
    """中标日期：支持 2025/9/8 与 2025-09-08 两种格式。"""
    if value is None:
        return None
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y/%-m/%-d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_order_fields(row: dict[str, str]) -> dict[str, Any]:
    """从行数据提取 Order 标识字段。"""
    order_fields: dict[str, Any] = {}
    for col, attr in ORDER_FIELD_MAP.items():
        value = _empty_to_none(row.get(col, ""))
        if attr == "win_bid_date":
            order_fields[attr] = _parse_win_bid_date(value)
        else:
            order_fields[attr] = value
    return order_fields


def _parse_feature_fields(row: dict[str, str]) -> dict[str, Any]:
    """从行数据提取 OrderFeature 特征字段。"""
    feature_fields: dict[str, Any] = {}
    for col, attr in FEATURE_FIELD_MAP.items():
        value = _empty_to_none(row.get(col, ""))
        if value is None:
            feature_fields[attr] = None
        elif _is_int_field(attr):
            feature_fields[attr] = _to_int(value)
        elif _is_float_field(attr):
            feature_fields[attr] = _to_float(value)
        elif _is_bigint_field(attr):
            feature_fields[attr] = _to_int(value)
        elif _is_bool_field(attr):
            feature_fields[attr] = _to_bool(value)
        else:
            # supplier_categories 等字符串字段
            feature_fields[attr] = value
    return feature_fields


def _parse_extra_features(row: dict[str, str]) -> dict[str, Any] | None:
    """提取结构性扩展列（中标月份/是否月末/是否季末）到 JSON。"""
    extra: dict[str, Any] = {}
    for col in EXTRA_FEATURE_COLUMNS:
        value = _empty_to_none(row.get(col, ""))
        if value is not None:
            extra[col] = _to_int(value) if col != "中标月份" else value
    return extra or None


def parse_csv_text(text: str) -> list[dict[str, str]]:
    """解析 CSV 文本为行列表（dict: 列名→原始字符串值）。

    Args:
        text: 已解码的 CSV 文本

    Returns:
        行列表，每行是 列名→值 的字典

    Raises:
        CSVParseError: 空内容或缺失必填列
    """
    if not text.strip():
        raise CSVParseError("文件为空或格式错误")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CSVParseError("文件为空或格式错误")

    _check_columns(list(reader.fieldnames))
    return [row for row in reader if any((v or "").strip() for v in row.values())]


def _sync_pay_status(order: Order, feature: OrderFeature, actual_pay_duration: int | None) -> None:
    """根据「实际支付时长_天」同步订单支付状态。

    有值=已支付 → pay_status='PAID'；无值=未支付 → pay_status=None。
    batch.py 判断未支付用 Order.pay_status，导入时同步保证跑批正确识别。
    """
    if actual_pay_duration is not None:
        order.pay_status = "PAID"
        if order.pay_time is None:
            order.pay_time = datetime.utcnow()
    else:
        order.pay_status = None
        # pay_time 保留首次值不清（审计），actual_pay_duration 由 feature 反映


def ingest_rows(db: Session, rows: list[dict[str, str]]) -> UploadResult:
    """把解析出的行入库：去重 + orders/order_features 1:1。

    重复订单（service_fee_order_no 已存在）→ 更新支付状态（非跳过）：
    按 CSV「实际支付时长_天」同步 Order.pay_status，其他特征保持首次导入值。

    Args:
        db: 数据库会话
        rows: parse_csv_text 的返回值

    Returns:
        UploadResult(inserted, skipped, updated, errors)
    """
    inserted = 0
    skipped = 0
    updated = 0
    errors: list[str] = []

    for idx, row in enumerate(rows, start=2):  # start=2 对应 CSV 行号（1 为表头）
        order_fields = _parse_order_fields(row)
        order_no = order_fields.get("service_fee_order_no")
        if not order_no:
            errors.append(f"第{idx}行: 缺失服务费订单号，跳过")
            continue

        feature_fields = _parse_feature_fields(row)
        actual_pay_duration = feature_fields.get("actual_pay_duration_days")

        existing = (
            db.query(Order)
            .filter(Order.service_fee_order_no == order_no)
            .first()
        )
        if existing is not None:
            # 重复订单：更新支付状态（非跳过）
            existing_feature = (
                db.query(OrderFeature)
                .filter(OrderFeature.order_id == existing.id)
                .first()
            )
            if existing_feature is not None:
                existing_feature.actual_pay_duration_days = actual_pay_duration
            _sync_pay_status(existing, existing_feature, actual_pay_duration)
            updated += 1
            continue

        order = Order(**order_fields)
        db.add(order)
        db.flush()  # 拿到 order.id

        extra = _parse_extra_features(row)
        feature = OrderFeature(order_id=order.id, **feature_fields, extra_features=extra)
        db.add(feature)
        # 新订单也同步支付状态
        _sync_pay_status(order, feature, actual_pay_duration)
        inserted += 1

    db.commit()
    return UploadResult(inserted=inserted, skipped=skipped, updated=updated, errors=errors)


def upload_csv_bytes(db: Session, raw: bytes) -> UploadResult:
    """端到端：字节 → 解码 → 解析 → 入库。"""
    text = detect_and_decode(raw)
    rows = parse_csv_text(text)
    return ingest_rows(db, rows)


__all__ = [
    "CSVParseError",
    "EncodingError",
    "UploadResult",
    "parse_csv_text",
    "ingest_rows",
    "upload_csv_bytes",
]
