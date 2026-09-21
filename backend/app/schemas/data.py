"""data-001 数据接入相关 schema。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import APIResponse, Pagination


class BatchResultOut(BaseModel):
    """跑批结果摘要（待支付导入后自动跑批返回）。"""

    generated: int
    finalized: int
    by_tier: dict[str, int]


class UploadSummary(BaseModel):
    """上传结果统计。"""

    inserted: int
    skipped: int
    updated: int = 0  # 重复订单更新支付状态数
    errors: list[str] = []
    batch_result: BatchResultOut | None = None  # 待支付导入后自动跑批结果；已支付导入为 None


class OrderOut(BaseModel):
    """订单标识与状态。"""

    id: int
    supplier_no: str
    supplier_name: str
    biz_no: str
    service_fee_order_no: str
    subject_name: str | None = None
    tender_type_desc: str | None = None
    purchase_type_desc: str | None = None
    bid_category: str | None = None
    contract_type: str | None = None
    subject_estimate_amount: float | None = None
    engineering_bureau: str | None = None
    subsidiary: str | None = None
    win_bid_date: date | None = None
    order_generated_date: date | None = None
    register_area: str | None = None
    register_province: str | None = None
    pay_status: str | None = None
    pay_time: datetime | None = None
    actual_pay_duration_days: int | None = None
    risk_prob: float | None = None
    risk_tier: str | None = None
    risk_import_time: datetime | None = None
    collection_state: str = "NO_NEED"


class FeatureOut(BaseModel):
    """订单特征（非标识字段）。"""

    order_id: int
    history_fee_order_count: int | None = None
    last_pay_duration_days: int | None = None
    avg_pay_duration_days: float | None = None
    fwsc_history_pay_amount: float | None = None
    signup_count: int | None = None
    bidding_count: int | None = None
    win_count: int | None = None
    win_rate: float | None = None
    active_90d: int | None = None
    first_win_interval_days: int | None = None
    is_member_at_win: bool | None = None
    member_purchase_count_before_win: int | None = None
    register_fund: int | None = None
    register_interval_days: int | None = None
    in_date_interval_days: int | None = None
    entry_interval_days: int | None = None
    supplier_categories: str | None = None
    ads_win_rate: float | None = None
    high_quality_cnt: int | None = None
    cooperate_org_num: int | None = None
    total_perform_project_num: int | None = None
    extra_features: dict[str, Any] | None = None


class OrderDetailOut(BaseModel):
    """订单 + 特征详情。"""

    order: OrderOut
    feature: FeatureOut | None = None


class OrderListOut(BaseModel):
    """订单分页列表。"""

    items: list[OrderOut]
    total: int
    page: int = 1
    limit: int = 50


class OrderListResponse(APIResponse[OrderListOut]):
    """订单列表响应。"""


class OrderDetailResponse(APIResponse[OrderDetailOut]):
    """订单详情响应。"""
