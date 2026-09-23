"""data-002 数据接入路由：待支付/已支付 CSV 导入 + 订单查询。

导入需 ADMIN 权限；列表/详情需登录。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_role
from app.models.order import Order, OrderFeature
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.data import (
    BatchResultOut,
    FeatureOut,
    OrderDetailOut,
    OrderListOut,
    OrderOut,
    UploadSummary,
)
from app.services.data_ingestion.parser import (
    CSVParseError,
    EncodingError,
    upload_paid_csv,
    upload_pending_csv,
)
from app.services.task_engine import BatchNotReadyError, run_batch

router = APIRouter()

_ALLOWED_SUFFIXES = {".csv"}


def _validate_csv(file: UploadFile) -> bytes:
    """校验 CSV 文件并返回原始字节。"""
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 CSV 文件",
        )
    raw = file.file.read()
    if not raw or not raw.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件为空或格式错误",
        )
    return raw


def _parse_or_400(result_fn):
    """执行上传并捕获解析异常 → 400。"""
    try:
        return result_fn()
    except EncodingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except CSVParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post("/upload-pending", response_model=APIResponse[UploadSummary])
def upload_pending(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[UploadSummary]:
    """导入待支付订单 CSV（全量/增量共用）。仅 ADMIN。

    入库未支付订单 + 特征 + 风险概率（经阈值映射档位）。
    重复订单更新风险概率 + 特征。
    导入成功后自动触发跑批（推进状态机 + 生成任务），响应含 batch_result。
    """
    raw = _validate_csv(file)
    result = _parse_or_400(lambda: upload_pending_csv(db, raw))
    # 导入后自动跑批（推进状态机 + 生成任务）；跑批失败不阻断导入（已入库）
    batch_result = None
    try:
        batch = run_batch(db, today=date.today(), recalc_risk=False)
        batch_result = BatchResultOut(
            generated=batch.generated,
            deleted=batch.deleted,
            skipped=batch.skipped,
            by_tier=batch.by_tier,
        )
    except BatchNotReadyError:
        # 无生效风险档配置时跑批跳过（导入数据已入库，跑批待配置就绪后定时/启动触发）
        pass
    return APIResponse(
        data=UploadSummary(
            inserted=result.inserted,
            skipped=result.skipped,
            updated=result.updated,
            errors=result.errors,
            batch_result=batch_result,
        )
    )


@router.post("/upload-paid", response_model=APIResponse[UploadSummary])
def upload_paid(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[UploadSummary]:
    """导入已支付订单 CSV。仅 ADMIN。

    按服务费订单号匹配待支付订单，回写 pay_status=PAID + pay_time + 实际支付时长。
    无匹配 / 已 PAID → 跳过。
    """
    raw = _validate_csv(file)
    result = _parse_or_400(lambda: upload_paid_csv(db, raw))
    return APIResponse(data=UploadSummary(**result.__dict__))


@router.get("/orders", response_model=APIResponse[OrderListOut])
def list_orders(
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> APIResponse[OrderListOut]:
    """订单分页列表。"""
    page = max(page, 1)
    limit = max(1, min(limit, 500))
    offset = (page - 1) * limit

    total = db.query(Order).count()
    orders = (
        db.query(Order)
        .order_by(Order.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = [OrderOut.model_validate(o, from_attributes=True) for o in orders]
    return APIResponse(
        data=OrderListOut(items=items, total=total, page=page, limit=limit)
    )


@router.get("/orders/{order_id}", response_model=APIResponse[OrderDetailOut])
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> APIResponse[OrderDetailOut]:
    """订单 + 特征详情。"""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在"
        )
    feature = (
        db.query(OrderFeature).filter(OrderFeature.order_id == order_id).first()
    )
    return APIResponse(
        data=OrderDetailOut(
            order=OrderOut.model_validate(order, from_attributes=True),
            feature=(
                FeatureOut.model_validate(feature, from_attributes=True)
                if feature
                else None
            ),
        )
    )
