"""ORM 模型集合。

集中导入所有模型类，Alembic env.py 的 autogenerate 依赖此导入
（否则检测不到表，生成空迁移）。
"""

from app.models.ai_config import AIConfig
from app.models.base import Base, CreatedAtMixin, TimestampMixin
from app.models.order import Order, OrderFeature
from app.models.risk import CollectionSchedule, RiskConfig
from app.models.task import Task, TaskResult
from app.models.talk import AIConversation, TalkTemplate
from app.models.user import User

__all__ = [
    "Base",
    "TimestampMixin",
    "CreatedAtMixin",
    "Order",
    "OrderFeature",
    "RiskConfig",
    "CollectionSchedule",
    "Task",
    "TaskResult",
    "User",
    "TalkTemplate",
    "AIConversation",
    "AIConfig",
]
