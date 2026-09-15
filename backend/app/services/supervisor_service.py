"""主管视图服务（supervisor 增强需求）。

员工绩效聚合：每位催收员的待处理/进行中/已完成任务数 + 回款数 + 回款率。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.task import Task, TaskResult
from app.models.user import User

_PAID = "PAID"


@dataclass(frozen=True)
class StaffPerformance:
    """单个催收员的绩效。"""

    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    pending_count: int = 0
    in_progress_count: int = 0
    done_count: int = 0
    paid_count: int = 0
    paid_rate: float = 0.0


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def get_staff_performance(db: Session) -> list[StaffPerformance]:
    """聚合所有催收员的任务统计。

    统计口径：
    - pending_count: status=PENDING（已分配待领取，含 PROMISE 改期回 PENDING）
    - in_progress_count: status=IN_PROGRESS
    - done_count: status=DONE（终态，含 PAID/DISPUTE/LOST_CONTACT/OTHER）
    - paid_count: TaskResult.result=PAID 的明细数（按 collector_id）
    - paid_rate: paid_count / done_count
    """
    # 全部催收员（含停用，主管需看全貌）
    collectors = (
        db.query(User).filter(User.role == "COLLECTOR").order_by(User.id).all()
    )
    if not collectors:
        return []

    collector_ids = [c.id for c in collectors]

    # 按催收员 + 状态聚合任务数
    task_rows = (
        db.query(Task.assignee_id, Task.status, func.count(Task.id))
        .filter(
            Task.assignee_id.in_(collector_ids),
            Task.status.in_(("PENDING", "IN_PROGRESS", "DONE")),
        )
        .group_by(Task.assignee_id, Task.status)
        .all()
    )
    status_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for assignee_id, st, cnt in task_rows:
        if assignee_id is not None:
            status_counts[assignee_id][st] = cnt

    # 按催收员聚合回款数（TaskResult PAID 明细）
    paid_rows = (
        db.query(TaskResult.collector_id, func.count(TaskResult.id))
        .filter(
            TaskResult.collector_id.in_(collector_ids),
            TaskResult.result == _PAID,
        )
        .group_by(TaskResult.collector_id)
        .all()
    )
    paid_counts: dict[int, int] = {cid: cnt for cid, cnt in paid_rows if cid is not None}

    result: list[StaffPerformance] = []
    for c in collectors:
        sc = status_counts.get(c.id, {})
        pending = sc.get("PENDING", 0)
        in_progress = sc.get("IN_PROGRESS", 0)
        done = sc.get("DONE", 0)
        paid = paid_counts.get(c.id, 0)
        result.append(
            StaffPerformance(
                id=c.id,
                username=c.username,
                display_name=c.display_name,
                role=c.role,
                is_active=c.is_active,
                pending_count=pending,
                in_progress_count=in_progress,
                done_count=done,
                paid_count=paid,
                paid_rate=_rate(paid, done),
            )
        )
    return result


__all__ = ["StaffPerformance", "get_staff_performance"]
