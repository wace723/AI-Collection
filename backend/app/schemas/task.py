"""task-001/002 催收任务相关 schema。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class BatchRunOut(BaseModel):
    """一次跑批（生成阶段）的结果摘要。"""

    batch_id: str
    today: date
    scanned: int
    generated: int
    idempotent_skipped: int
    by_tier: dict[str, int]


class BatchStatusOut(BaseModel):
    """批次任务聚合状态（供跑批状态查询）。"""

    batch_id: str
    total: int
    by_status: dict[str, int]
    by_tier: dict[str, int]


class AssignmentRunOut(BaseModel):
    """一次分配的结果摘要。"""

    assigned: int
    skipped: int
    by_assignee: dict[int, int]
    assignee_names: dict[int, str]


class TaskOut(BaseModel):
    """任务详情（state machine 操作返回）。

    supplier_name/subject_name/subject_estimate_amount/win_bid_date 来自关联 Order，
    列表/详情统一返回（工作台展示用）。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    service_fee_order_no: str
    supplier_name: str = ""
    subject_name: str | None = None
    subject_estimate_amount: float | None = None
    win_bid_date: date | None = None
    risk_tier: str
    scene: str
    day_offset: int
    due_date: date
    status: str
    assignee_id: int | None = None
    assigned_at: datetime | None = None
    result: str | None = None
    result_note: str | None = None
    next_followup_date: date | None = None
    batch_id: str


class TaskResultIn(BaseModel):
    """回填处理结果入参。"""

    result: Literal["PAID", "PROMISE", "DISPUTE", "LOST_CONTACT", "OTHER"]
    note: str | None = None
    next_followup_date: date | None = None
    talk_used: str | None = None


class OrderBriefOut(BaseModel):
    """任务详情内嵌的订单摘要（含标的/品类/支付等完整字段）。"""

    model_config = ConfigDict(from_attributes=True)

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


class FeatureBriefOut(BaseModel):
    """任务详情内嵌的用户特征摘要（完整画像字段，分类展示用）。"""

    model_config = ConfigDict(from_attributes=True)

    # A 类 · 缴费历史
    history_fee_order_count: int | None = None
    last_pay_duration_days: int | None = None
    avg_pay_duration_days: float | None = None
    # B 类 · 活跃度与支付
    fwsc_history_pay_amount: float | None = None
    signup_count: int | None = None
    bidding_count: int | None = None
    win_count: int | None = None
    win_rate: float | None = None
    active_90d: int | None = None
    first_win_interval_days: int | None = None
    is_member_at_win: bool | None = None
    member_purchase_count_before_win: int | None = None
    # C 类 · 资质与标签
    register_fund: int | None = None
    register_interval_days: int | None = None
    in_date_interval_days: int | None = None
    entry_interval_days: int | None = None
    supplier_categories: str | None = None
    ads_win_rate: float | None = None
    high_quality_cnt: int | None = None
    cooperate_org_num: int | None = None
    total_perform_project_num: int | None = None


class TaskDetailOut(TaskOut):
    """任务详情（含订单摘要 + 特征摘要）。"""

    order: OrderBriefOut
    feature: FeatureBriefOut | None = None


__all__ = [
    "BatchRunOut",
    "BatchStatusOut",
    "AssignmentRunOut",
    "TaskOut",
    "TaskResultIn",
    "OrderBriefOut",
    "FeatureBriefOut",
    "TaskDetailOut",
]
