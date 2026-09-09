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
    """任务详情（state machine 操作返回）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    service_fee_order_no: str
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


__all__ = [
    "BatchRunOut",
    "BatchStatusOut",
    "AssignmentRunOut",
    "TaskOut",
    "TaskResultIn",
]
