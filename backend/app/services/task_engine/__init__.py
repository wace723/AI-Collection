"""task_engine：催收任务生成与分配。

对外暴露稳定入口（task-001 起）：
- generate_tasks / run_batch：任务生成跑批
- BatchResult / BatchNotReadyError
task-002 将在此追加分配逻辑（assign_tasks 等）。
"""

from app.services.task_engine.batch import (
    BatchNotReadyError,
    BatchResult,
    generate_tasks,
    run_batch,
)

__all__ = [
    "BatchResult",
    "BatchNotReadyError",
    "generate_tasks",
    "run_batch",
]
