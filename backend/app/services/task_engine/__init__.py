"""task_engine：催收任务生成、分配与状态机。

对外暴露稳定入口：
- generate_tasks / run_batch：任务生成跑批（task-001）
- assign_pending_tasks：任务分配（task-002）
- claim_task / submit_result：状态机流转（task-002 的 TC-TASK-11/12）
- reassign_task：主管手动改派（supervisor 增强需求，F-TASK-04）
"""

from app.services.task_engine.assignment import (
    AssignmentError,
    AssignmentResult,
    assign_pending_tasks,
)
from app.services.task_engine.batch import (
    BatchNotReadyError,
    BatchResult,
    generate_tasks,
    run_batch,
)
from app.services.task_engine.reassign import reassign_task
from app.services.task_engine.state import (
    TaskNotFoundError,
    TaskStateError,
    claim_task,
    submit_result,
)

__all__ = [
    "BatchResult",
    "BatchNotReadyError",
    "generate_tasks",
    "run_batch",
    "AssignmentResult",
    "AssignmentError",
    "assign_pending_tasks",
    "TaskNotFoundError",
    "TaskStateError",
    "claim_task",
    "submit_result",
    "reassign_task",
]
