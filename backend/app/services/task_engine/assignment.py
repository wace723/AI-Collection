"""催收任务分配（task-002）。

算法（docs/02 §4.2.3）：
1. 取所有 PENDING_ASSIGN 任务，按「风险档 HIGH>MEDIUM>LOW；同档按账龄倒序
   （due_date 升序：越早到期=账龄越大越优先）」排序。
2. 取活跃催收员，按 id 升序构建初始负载 = 当前 PENDING + IN_PROGRESS 任务数。
3. 逐任务分配给「当前负载最低」的催收员（tie 时取最小 id，由 dict 插入顺序保证），
   分配后该催收员负载 +1。

幂等：只处理 status=PENDING_ASSIGN 的任务；已分配(PENDING)/处理中(IN_PROGRESS)/
终态(DONE/CANCELLED)不会被再次分配。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.user import User

# 风险档优先级（数值越小越优先）
_RISK_PRIORITY = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# 计入「当前负载」的待处理状态
_ACTIVE_PROCESSING_STATUSES = ("PENDING", "IN_PROGRESS")


@dataclass(frozen=True)
class AssignmentResult:
    """一次分配的结果统计。"""

    assigned: int = 0
    skipped: int = 0  # 无可用催收员时未分配的任务数
    by_assignee: dict[int, int] = field(default_factory=dict)  # collector_id → 新分配数
    assignee_names: dict[int, str] = field(default_factory=dict)


class AssignmentError(ValueError):
    """分配前置条件不满足（如无活跃催收员）。"""


def _sort_key(task: Task) -> tuple[int, ...]:
    """排序键：风险档优先 → 账龄倒序（due_date 升序）→ id 升序兜底稳定。"""
    return (_RISK_PRIORITY.get(task.risk_tier, 99), task.due_date, task.id)


def _get_active_collectors(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(User.role == "COLLECTOR", User.is_active.is_(True))
        .order_by(User.id)
        .all()
    )


def _init_loads(db: Session, collector_ids: list[int]) -> dict[int, int]:
    """各催收员当前待处理任务数（PENDING + IN_PROGRESS）。"""
    loads = {cid: 0 for cid in collector_ids}
    if not collector_ids:
        return loads
    rows = (
        db.query(Task.assignee_id)
        .filter(
            Task.assignee_id.in_(collector_ids),
            Task.status.in_(_ACTIVE_PROCESSING_STATUSES),
        )
        .all()
    )
    for (assignee_id,) in rows:
        loads[assignee_id] = loads.get(assignee_id, 0) + 1
    return loads


def assign_pending_tasks(db: Session) -> AssignmentResult:
    """把所有 PENDING_ASSIGN 任务按「高风险优先 + 负载均衡」分配给活跃催收员。

    Raises:
        AssignmentError: 无活跃催收员
    """
    collectors = _get_active_collectors(db)
    pending = db.query(Task).filter(Task.status == "PENDING_ASSIGN").all()

    if not collectors:
        # 无催收员：不分配，记录待分配数
        return AssignmentResult(assigned=0, skipped=len(pending))

    loads = _init_loads(db, [c.id for c in collectors])
    pending.sort(key=_sort_key)

    now = datetime.now(timezone.utc)
    assigned = 0
    by_assignee: dict[int, int] = defaultdict(int)

    for task in pending:
        assignee_id = min(loads, key=loads.get)  # 当前负载最低者；tie 取最小 id
        task.assignee_id = assignee_id
        task.status = "PENDING"
        task.assigned_at = now
        loads[assignee_id] += 1
        assigned += 1
        by_assignee[assignee_id] += 1

    db.commit()
    return AssignmentResult(
        assigned=assigned,
        skipped=0,
        by_assignee=dict(by_assignee),
        assignee_names={c.id: c.username for c in collectors},
    )


__all__ = ["AssignmentResult", "AssignmentError", "assign_pending_tasks"]
