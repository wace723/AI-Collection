"""催收任务状态机（task-002 的 TC-TASK-11/12 部分）。

状态流转（docs/02 §4.3）：
    PENDING_ASSIGN ──分配──▶ PENDING ──领取──▶ IN_PROGRESS ──回填──▶ DONE(终态)
                                                           │
                                                           └─ PROMISE → 改期 → PENDING(承诺日再催)

终态（DONE / CANCELLED）不可再变更。
催收员只能操作分配给自己的任务；SUPERVISOR/ADMIN 可改派/代理。
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.task import Task, TaskResult
from app.models.user import User

# 终态：不允许再 claim / result
_TERMINAL_STATUSES = ("DONE", "CANCELLED")

# 回填结果枚举
_RESULT_PROMISE = "PROMISE"
_TERMINAL_RESULTS = ("PAID", "DISPUTE", "LOST_CONTACT", "OTHER")
_ALL_RESULTS = (_RESULT_PROMISE,) + _TERMINAL_RESULTS


class TaskNotFoundError(LookupError):
    """任务不存在。"""


class TaskStateError(ValueError):
    """状态机规则违反（状态不允许、无权操作、PROMISE 缺改期日等）。"""


def _get_task(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise TaskNotFoundError(f"任务 {task_id} 不存在")
    return task


def _ensure_operator(task: Task, user: User) -> None:
    """催收员只能操作自己的任务；SUPERVISOR/ADMIN 放行。"""
    if user.role == "COLLECTOR" and task.assignee_id != user.id:
        raise TaskStateError("无权操作他人任务")


def claim_task(db: Session, task_id: int, user: User) -> Task:
    """领取任务：PENDING → IN_PROGRESS。

    - 仅 PENDING 可领取（PENDING_ASSIGN 尚未分配，IN_PROGRESS 已领取，终态不可领）
    - COLLECTOR 只能领取分配给自己的任务
    """
    task = _get_task(db, task_id)
    if task.status in _TERMINAL_STATUSES:
        raise TaskStateError(f"终态任务({task.status})不可领取")
    if task.status != "PENDING":
        raise TaskStateError(f"仅 PENDING 任务可领取，当前状态={task.status}")
    _ensure_operator(task, user)

    task.status = "IN_PROGRESS"
    db.commit()
    return task


def submit_result(
    db: Session,
    task_id: int,
    user: User,
    *,
    result: str,
    note: str | None = None,
    next_followup_date: date | None = None,
    talk_used: str | None = None,
) -> Task:
    """回填处理结果：IN_PROGRESS → DONE(终态) 或 PENDING(PROMISE 改期)。

    - 仅 IN_PROGRESS 可回填
    - result=PROMISE 必须提供 next_followup_date，任务回到 PENDING 等待承诺日再催
    - PAID/DISPUTE/LOST_CONTACT/OTHER → DONE 终态
    - 写一条 TaskResult 明细（支持同一任务多次跟进）
    """
    if result not in _ALL_RESULTS:
        raise TaskStateError(f"未知结果类型: {result}")

    task = _get_task(db, task_id)
    if task.status in _TERMINAL_STATUSES:
        raise TaskStateError(f"终态任务({task.status})不可回填")
    if task.status != "IN_PROGRESS":
        raise TaskStateError(f"仅 IN_PROGRESS 任务可回填，当前状态={task.status}")
    _ensure_operator(task, user)

    if result == _RESULT_PROMISE and next_followup_date is None:
        raise TaskStateError("承诺还款(PROMISE)必须提供 next_followup_date")

    task.result = result
    task.result_note = note
    task.next_followup_date = next_followup_date

    if result == _RESULT_PROMISE:
        # 改期：承诺日再催，回到待处理（保留 assignee 不变，便于同催收员跟进）
        task.status = "PENDING"
    else:
        task.status = "DONE"

    db.add(
        TaskResult(
            task_id=task.id,
            collector_id=user.id,
            result=result,
            note=note,
            talk_used=talk_used,
        )
    )
    db.commit()
    return task


__all__ = [
    "TaskNotFoundError",
    "TaskStateError",
    "claim_task",
    "submit_result",
]
