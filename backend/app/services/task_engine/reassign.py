"""手动改派任务（supervisor 增强需求，F-TASK-04 P1）。

主管可把任务从 A 催收员改派给 B 催收员：
- 终态（DONE/CANCELLED）不可改派
- 新催收员必须存在、是 COLLECTOR、且 is_active
- 改派后保持 IN_PROGRESS（不再退回 PENDING，因已去掉领取步骤）
- data-003：改派不改 Order.collection_state（催收状态由跑批/回填/已支付导入驱动）
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.user import User
from app.services.task_engine.state import TaskNotFoundError, TaskStateError

_TERMINAL_STATUSES = ("DONE", "CANCELLED")


def reassign_task(db: Session, task_id: int, new_assignee_id: int) -> Task:
    """把任务改派给新催收员。

    Raises:
        TaskNotFoundError: 任务不存在
        TaskStateError: 任务终态不可改派 / 新催收员无效
    """
    task = db.get(Task, task_id)
    if task is None:
        raise TaskNotFoundError(f"任务 {task_id} 不存在")

    if task.status in _TERMINAL_STATUSES:
        raise TaskStateError(f"终态任务({task.status})不可改派")

    new_assignee = db.get(User, new_assignee_id)
    if new_assignee is None or not new_assignee.is_active:
        raise TaskStateError(f"目标催收员 {new_assignee_id} 不存在或已停用")
    if new_assignee.role != "COLLECTOR":
        raise TaskStateError("只能改派给催收员角色（COLLECTOR）")

    task.assignee_id = new_assignee_id
    task.assigned_at = datetime.now(timezone.utc)
    # 保持 IN_PROGRESS（PENDING_ASSIGN 改派也设为 IN_PROGRESS，让新催收员直接处理）
    task.status = "IN_PROGRESS"

    db.commit()
    return task


__all__ = ["reassign_task"]

