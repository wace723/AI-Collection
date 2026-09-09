"""data-001 数据接入路由：CSV 上传 + 订单查询。

上传需 ADMIN 权限；列表/详情需登录。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_role
from app.models.order import Order, OrderFeature
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.data import (
    FeatureOut,
    OrderDetailOut,
    OrderListOut,
    OrderOut,
    UploadSummary,
)
from app.schemas.risk import RecalcRiskSummary
from app.services.data_ingestion.parser import (
    CSVParseError,
    EncodingError,
    upload_csv_bytes,
)
from app.services.risk_engine import recalculate_risks

router = APIRouter()

# 允许的文件扩展名
_ALLOWED_SUFFIXES = {".csv"}


@router.post("/upload", response_model=APIResponse[UploadSummary])
def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[UploadSummary]:
    """上传 CSV 并解析入库（仅 ADMIN）。

    自动识别 GBK/UTF-8 编码，按 service_fee_order_no 去重。
    """
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

    try:
        result = upload_csv_bytes(db, raw)
    except EncodingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except CSVParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

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


@router.post(
    "/orders/recalc-risk", response_model=APIResponse[RecalcRiskSummary]
)
def recalc_risk(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[RecalcRiskSummary]:
    """批量重算风险概率与档位（仅 ADMIN）。

    对全部订单调用当前 RiskProvider（默认 mock）算概率，
    按 active 风险档配置映射 HIGH/MEDIUM/LOW，回写订单。
    """
    result = recalculate_risks(db)
    return APIResponse(data=RecalcRiskSummary(**result.__dict__))


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
