"""催收任务状态机（data-003 回填两分类推进状态）。

状态流转：
    PENDING_ASSIGN ──分配──▶ IN_PROGRESS ──回填REACHED──▶ DONE(终态)
                                    │
                                    └─ 回填UNREACHED ──▶ 仍 IN_PROGRESS（同日可反复重试）

分配后直接 IN_PROGRESS，催收员无需领取。终态（DONE/CANCELLED）不可再变更。
回填结果两分类（data-003，BREAKING）：
- REACHED（已接通）：Task→DONE 终态，Order.collection_state→COLLECTED（该轮已催收）
- UNREACHED（未接通）：Task 保持 IN_PROGRESS，Order.collection_state 保持 PENDING_COLLECTION，
  同日可反复回填（每次写一条 TaskResult 明细），直到 REACHED 或进入下一轮

催收员只能操作分配给自己的任务；SUPERVISOR/ADMIN 可改派/代理。
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.task import Task, TaskResult
from app.models.user import User
from app.services.task_engine.states import (
    COLLECTED,
    DONE,
    IN_PROGRESS,
    PENDING_COLLECTION,
    REACHED,
    RESULT_VALUES,
    TERMINAL_STATUSES,
)


class TaskNotFoundError(LookupError):
    """任务不存在。"""


class TaskPermissionError(PermissionError):
    """越权操作（催收员操作他人任务）。映射为 403。"""


class TaskStateError(ValueError):
    """状态机规则违反（状态不允许、未知结果等）。映射为 409。"""


def _get_task(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise TaskNotFoundError(f"任务 {task_id} 不存在")
    return task


def _ensure_operator(task: Task, user: User) -> None:
    """催收员只能操作自己的任务；SUPERVISOR/ADMIN 放行。"""
    if user.role == "COLLECTOR" and task.assignee_id != user.id:
        raise TaskPermissionError("无权操作他人任务")


def claim_task(db: Session, task_id: int, user: User) -> Task:
    """领取任务：PENDING → IN_PROGRESS。

    保留函数兼容历史（data-003 后分配直接 IN_PROGRESS，无需领取）。
    - 仅 PENDING 可领取（PENDING_ASSIGN 尚未分配，IN_PROGRESS 已领取，终态不可领）
    - COLLECTOR 只能领取分配给自己的任务
    """
    task = _get_task(db, task_id)
    if task.status in TERMINAL_STATUSES:
        raise TaskStateError(f"终态任务({task.status})不可领取")
    if task.status != "PENDING":
        raise TaskStateError(f"仅 PENDING 任务可领取，当前状态={task.status}")
    _ensure_operator(task, user)

    task.status = IN_PROGRESS
    db.commit()
    return task


def submit_result(
    db: Session,
    task_id: int,
    user: User,
    *,
    result: str,
    note: str | None = None,
    talk_used: str | None = None,
    next_followup_date: date | None = None,  # 保留入参兼容旧调用，data-003 不再使用
) -> Task:
    """回填处理结果：IN_PROGRESS → DONE(REACHED) 或保持 IN_PROGRESS(UNREACHED)。

    data-003 两分类（BREAKING）：
    - result=REACHED（已接通）：Task.status→DONE 终态，Order.collection_state→COLLECTED，
      写一条 TaskResult 明细（含自由文本反馈 note）
    - result=UNREACHED（未接通）：Task.status 保持 IN_PROGRESS，
      Order.collection_state 保持 PENDING_COLLECTION，写一条 TaskResult 明细，
      同日可反复回填直到 REACHED 或进入下一轮

    - 仅 IN_PROGRESS 可回填；终态不可回填（409）
    - COLLECTOR 只能回填自己任务（403）；SUPERVISOR/ADMIN 可代理
    - next_followup_date 入参保留兼容旧调用，data-003 不再使用（移除 PROMISE 改期分支）
    """
    if result not in RESULT_VALUES:
        raise TaskStateError(f"未知结果类型: {result}")

    task = _get_task(db, task_id)
    # 越权检查优先于状态检查（403 优先于 409）
    _ensure_operator(task, user)
    if task.status in TERMINAL_STATUSES:
        raise TaskStateError(f"终态任务({task.status})不可回填")
    if task.status != IN_PROGRESS:
        raise TaskStateError(f"仅 IN_PROGRESS 任务可回填，当前状态={task.status}")

    task.result = result
    task.result_note = note

    if result == REACHED:
        # 已接通：该轮已催收，Task 终态，Order 推进已催收
        task.status = DONE
        order = db.get(Order, task.order_id)
        if order is not None and order.collection_state == PENDING_COLLECTION:
            order.collection_state = COLLECTED
    # UNREACHED：保持 IN_PROGRESS，Order 保持 PENDING_COLLECTION（不动）

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
    "TaskPermissionError",
    "TaskStateError",
    "claim_task",
    "submit_result",
]
