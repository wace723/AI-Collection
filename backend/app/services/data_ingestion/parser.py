"""CSV 解析与入库服务（data-002 重构）。

两条导入路径：
1. 待支付订单导入（ingest_pending_rows）：入库未支付订单+特征+风险概率，重复更新风险概率/特征
2. 已支付订单导入（ingest_paid_rows）：按 service_fee_order_no 匹配回写支付状态

风险概率从 CSV「风险概率」列读取，经 tier_mapper 阈值映射档位。
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
    EXTRA_FEATURE_COLUMNS,
    FEATURE_FIELD_MAP,
    ORDER_FIELD_MAP,
    PAID_ORDER_COLUMNS,
    PENDING_ORDER_COLUMNS,
    REQUIRED_COLUMNS,
    _is_bigint_field,
    _is_bool_field,
    _is_float_field,
    _is_int_field,
)
from app.services.data_ingestion.encoding import EncodingError, detect_and_decode
from app.services.risk_engine.tier_mapper import get_active_thresholds, map_tier


class CSVParseError(ValueError):
    """CSV 内容或结构错误，对应 400。"""


@dataclass(frozen=True)
class UploadResult:
    """上传结果统计。"""

    inserted: int = 0
    skipped: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)


def _check_columns(header: list[str], expected: tuple[str, ...]) -> None:
    """校验表头：必填列必须齐全。缺失则抛 CSVParseError。"""
    header_set = {h.strip() for h in header}
    missing = [c for c in REQUIRED_COLUMNS if c not in header_set]
    if missing:
        raise CSVParseError(f"缺失必填列: {', '.join(missing)}")


def _empty_to_none(value: str) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
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


_DATE_FORMATS = ("%Y/%m/%d", "%Y-%m-%d", "%Y/%-m/%-d")


def _parse_date(value: str | None) -> date | None:
    """日期解析：支持 2025/9/8 与 2025-09-08。"""
    if value is None:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    """支付日期解析：支持 2025/9/8 或 2025-09-08（时间部分可选）。"""
    if value is None:
        return None
    # 尝试带时间
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    # 仅日期
    d = _parse_date(value)
    return datetime(d.year, d.month, d.day) if d else None


def _parse_order_fields(row: dict[str, str]) -> dict[str, Any]:
    """从行数据提取 Order 字段（含类型转换）。"""
    order_fields: dict[str, Any] = {}
    for col, attr in ORDER_FIELD_MAP.items():
        value = _empty_to_none(row.get(col, ""))
        if attr == "win_bid_date":
            order_fields[attr] = _parse_date(value)
        elif attr == "order_generated_date":
            order_fields[attr] = _parse_date(value)
        elif attr == "pay_time":
            order_fields[attr] = _parse_datetime(value)
        elif attr in ("risk_prob", "subject_estimate_amount"):
            order_fields[attr] = _to_float(value)
        elif attr == "actual_pay_duration_days":
            order_fields[attr] = _to_int(value)
        else:
            order_fields[attr] = value
    return order_fields


def _parse_feature_fields(row: dict[str, str]) -> dict[str, Any]:
    """从行数据提取 OrderFeature 字段。"""
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


def _map_risk_tier(db: Session, risk_prob: float | None) -> str | None:
    """风险概率经阈值映射档位。prob 为 None → None。"""
    if risk_prob is None:
        return None
    thresholds = get_active_thresholds(db)
    return map_tier(risk_prob, thresholds)


def parse_csv_text(text: str, expected: tuple[str, ...]) -> list[dict[str, str]]:
    """解析 CSV 文本为行列表（dict: 列名→原始字符串值）。

    Args:
        text: 已解码的 CSV 文本
        expected: 期望的表头列集合（用于校验必填列）

    Raises:
        CSVParseError: 空内容或缺失必填列
    """
    if not text.strip():
        raise CSVParseError("文件为空或格式错误")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CSVParseError("文件为空或格式错误")

    _check_columns(list(reader.fieldnames), expected)
    return [row for row in reader if any((v or "").strip() for v in row.values())]


# ── 待支付订单导入 ────────────────────────────────────────────────


def ingest_pending_rows(db: Session, rows: list[dict[str, str]]) -> UploadResult:
    """待支付订单导入（全量/增量共用）。

    新订单：入库未支付订单 + 特征 + 风险概率（经阈值映射档位）。
    重复订单（service_fee_order_no 已存在）：更新风险概率 + 特征 + 标的等字段。
    """
    inserted = 0
    skipped = 0
    updated = 0
    errors: list[str] = []

    for idx, row in enumerate(rows, start=2):
        order_fields = _parse_order_fields(row)
        order_no = order_fields.get("service_fee_order_no")
        if not order_no:
            errors.append(f"第{idx}行: 缺失服务费订单号，跳过")
            continue

        risk_prob = order_fields.get("risk_prob")
        if risk_prob is not None and not (0 <= risk_prob <= 100):
            errors.append(f"第{idx}行: 风险概率 {risk_prob} 不在 [0,100]，置空")
            risk_prob = None
            order_fields["risk_prob"] = None

        existing = (
            db.query(Order)
            .filter(Order.service_fee_order_no == order_no)
            .first()
        )
        if existing is not None:
            # 重复订单：更新风险概率 + 特征 + 标的字段（非跳过）
            for attr, val in order_fields.items():
                if attr == "service_fee_order_no":
                    continue
                setattr(existing, attr, val)
            existing.risk_tier = _map_risk_tier(db, risk_prob)
            existing.risk_import_time = datetime.utcnow()
            # 更新特征
            existing_feature = (
                db.query(OrderFeature)
                .filter(OrderFeature.order_id == existing.id)
                .first()
            )
            if existing_feature is not None:
                feature_fields = _parse_feature_fields(row)
                extra = _parse_extra_features(row)
                for attr, val in feature_fields.items():
                    setattr(existing_feature, attr, val)
                if extra is not None:
                    existing_feature.extra_features = extra
            updated += 1
            continue

        # 新订单
        order = Order(**order_fields)
        order.risk_tier = _map_risk_tier(db, risk_prob)
        order.risk_import_time = datetime.utcnow() if risk_prob is not None else None
        db.add(order)
        db.flush()

        feature_fields = _parse_feature_fields(row)
        extra = _parse_extra_features(row)
        feature = OrderFeature(order_id=order.id, **feature_fields, extra_features=extra)
        db.add(feature)
        inserted += 1

    db.commit()
    return UploadResult(inserted=inserted, skipped=skipped, updated=updated, errors=errors)


# ── 已支付订单导入 ────────────────────────────────────────────────


def ingest_paid_rows(db: Session, rows: list[dict[str, str]]) -> UploadResult:
    """已支付订单导入：按 service_fee_order_no 匹配待支付订单，回写支付状态。

    命中且未支付 → pay_status=PAID + pay_time + actual_pay_duration_days，updated+1
    未命中 / 已 PAID → skipped+1
    不新建订单。
    """
    inserted = 0  # 恒为 0（不新建）
    skipped = 0
    updated = 0
    errors: list[str] = []

    for idx, row in enumerate(rows, start=2):
        order_no = _empty_to_none(row.get("服务费订单号", ""))
        if not order_no:
            errors.append(f"第{idx}行: 缺失服务费订单号，跳过")
            skipped += 1
            continue

        existing = (
            db.query(Order)
            .filter(Order.service_fee_order_no == order_no)
            .first()
        )
        if existing is None:
            skipped += 1
            errors.append(f"第{idx}行: 订单 {order_no} 不存在，跳过")
            continue
        if existing.pay_status == "PAID":
            skipped += 1
            continue

        # 回写支付状态（只动支付相关，不改风险/特征）
        pay_time = _parse_datetime(_empty_to_none(row.get("支付日期", "")))
        actual_duration = _to_int(_empty_to_none(row.get("实际支付时长_天", "")))
        existing.pay_status = "PAID"
        if pay_time is not None:
            existing.pay_time = pay_time
        if actual_duration is not None:
            existing.actual_pay_duration_days = actual_duration
        updated += 1

    db.commit()
    return UploadResult(inserted=inserted, skipped=skipped, updated=updated, errors=errors)


# ── 端到端入口 ────────────────────────────────────────────────────


def upload_pending_csv(db: Session, raw: bytes) -> UploadResult:
    """端到端：字节 → 解码 → 解析 → 待支付入库。"""
    text = detect_and_decode(raw)
    rows = parse_csv_text(text, PENDING_ORDER_COLUMNS)
    return ingest_pending_rows(db, rows)


def upload_paid_csv(db: Session, raw: bytes) -> UploadResult:
    """端到端：字节 → 解码 → 解析 → 已支付回写。"""
    text = detect_and_decode(raw)
    rows = parse_csv_text(text, PAID_ORDER_COLUMNS)
    return ingest_paid_rows(db, rows)


__all__ = [
    "CSVParseError",
    "EncodingError",
    "UploadResult",
    "parse_csv_text",
    "ingest_pending_rows",
    "ingest_paid_rows",
    "upload_pending_csv",
    "upload_paid_csv",
]
