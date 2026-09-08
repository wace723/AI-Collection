"""模型基类：Base / TimestampMixin / CreatedAtMixin。

实际定义在 core/database.py，这里 re-export 便于 models 模块统一引用。
"""

from app.core.database import Base, CreatedAtMixin, TimestampMixin

__all__ = ["Base", "TimestampMixin", "CreatedAtMixin"]
