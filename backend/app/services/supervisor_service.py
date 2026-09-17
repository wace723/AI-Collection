"""主管视图服务（supervisor 增强需求 + data-003 催收进度）。

员工绩效聚合：每位催收员的待处理/进行中/已完成任务数 + 回款数 + 回款率。
data-003 扩展：当天已接通/未接通/待处理计数（按 collection_state 与回填结果）。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.task import Task, TaskResult
from app.models.user import User
from app.services.task_engine.states import (
    DONE,
    IN_PROGRESS,
    PENDING_ASSIGN,
    PENDING_COLLECTION,
    REACHED,
    UNREACHED,
)


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
    # data-003：当天完成进度（已接通/未接通/待处理）
    today_reached: int = 0
    today_unreached: int = 0
    today_pending: int = 0


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def get_staff_performance(db: Session, *, today: date | None = None) -> list[StaffPerformance]:
    """聚合所有催收员的任务统计。

    统计口径：
    - pending_count: status=PENDING_ASSIGN（待分配）
    - in_progress_count: status=IN_PROGRESS
    - done_count: status=DONE（终态）
    - paid_count: TaskResult.result=REACHED 的明细数（按 collector_id，data-003 改为已接通口径）
    - paid_rate: paid_count / done_count
    - today_reached/today_unreached/today_pending: 当天该催收员的已接通/未接通/待处理任务数
    """
    resolved_today = today or date.today()
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
            Task.status.in_((PENDING_ASSIGN, IN_PROGRESS, DONE)),
        )
        .group_by(Task.assignee_id, Task.status)
        .all()
    )
    status_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for assignee_id, st, cnt in task_rows:
        if assignee_id is not None:
            status_counts[assignee_id][st] = cnt

    # 按催收员聚合已接通数（TaskResult REACHED 明细，data-003 改回款口径为已接通）
    paid_rows = (
        db.query(TaskResult.collector_id, func.count(TaskResult.id))
        .filter(
            TaskResult.collector_id.in_(collector_ids),
            TaskResult.result == REACHED,
        )
        .group_by(TaskResult.collector_id)
        .all()
    )
    paid_counts: dict[int, int] = {cid: cnt for cid, cnt in paid_rows if cid is not None}

    # data-003：当天完成进度（已接通/未接通/待处理）
    # 已接通 = 当天回填 REACHED 且任务 DONE 的明细数
    today_reached_rows = (
        db.query(TaskResult.collector_id, func.count(TaskResult.id))
        .filter(
            TaskResult.collector_id.in_(collector_ids),
            TaskResult.result == REACHED,
            func.date(TaskResult.created_at) == resolved_today,
        )
        .group_by(TaskResult.collector_id)
        .all()
    )
    today_reached_counts: dict[int, int] = {
        cid: cnt for cid, cnt in today_reached_rows if cid is not None
    }
    # 未接通 = 当天回填 UNREACHED 的明细数
    today_unreached_rows = (
        db.query(TaskResult.collector_id, func.count(TaskResult.id))
        .filter(
            TaskResult.collector_id.in_(collector_ids),
            TaskResult.result == UNREACHED,
            func.date(TaskResult.created_at) == resolved_today,
        )
        .group_by(TaskResult.collector_id)
        .all()
    )
    today_unreached_counts: dict[int, int] = {
        cid: cnt for cid, cnt in today_unreached_rows if cid is not None
    }
    # 待处理 = 当天该催收员名下 IN_PROGRESS 且未回填 REACHED 的任务数
    today_pending_rows = (
        db.query(Task.assignee_id, func.count(Task.id))
        .filter(
            Task.assignee_id.in_(collector_ids),
            Task.status == IN_PROGRESS,
        )
        .group_by(Task.assignee_id)
        .all()
    )
    today_pending_counts: dict[int, int] = {
        cid: cnt for cid, cnt in today_pending_rows if cid is not None
    }

    result: list[StaffPerformance] = []
    for c in collectors:
        sc = status_counts.get(c.id, {})
        pending = sc.get(PENDING_ASSIGN, 0)
        in_progress = sc.get(IN_PROGRESS, 0)
        done = sc.get(DONE, 0)
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
                today_reached=today_reached_counts.get(c.id, 0),
                today_unreached=today_unreached_counts.get(c.id, 0),
                today_pending=today_pending_counts.get(c.id, 0),
            )
        )
    return result


__all__ = ["StaffPerformance", "get_staff_performance"]
