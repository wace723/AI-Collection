"""催收任务与结果明细。"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin

# SQLite 下 BIGINT 主键/FK 不会自增（只有 INTEGER PRIMARY KEY 是 rowid 别名），
# variant 让 SQLite 退化为 INTEGER，PostgreSQL 保持 BIGINT。
_PK_BIGINT = BigInteger().with_variant(Integer, "sqlite")
_FK_BIGINT = BigInteger().with_variant(Integer, "sqlite")


class Task(Base, CreatedAtMixin):
    """催收任务。

    幂等关键：batch_id + order_id + day_offset 三元组唯一。
    该复合唯一约束留给 task-001 的迁移增量加，infra-001 仅声明普通列。
    """

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(_PK_BIGINT, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        _FK_BIGINT, ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    service_fee_order_no: Mapped[str] = mapped_column(String(64), index=True)
    risk_tier: Mapped[str] = mapped_column(String(8), index=True)
    scene: Mapped[str] = mapped_column(String(16))
    day_offset: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    # PENDING_ASSIGN / PENDING / IN_PROGRESS / DONE / CANCELLED
    status: Mapped[str] = mapped_column(String(16), default="PENDING_ASSIGN", index=True)
    assignee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime)
    # PAID / PROMISE / DISPUTE / LOST_CONTACT / OTHER
    result: Mapped[str | None] = mapped_column(String(16))
    result_note: Mapped[str | None] = mapped_column(Text)
    next_followup_date: Mapped[date | None] = mapped_column(Date)
    batch_id: Mapped[str] = mapped_column(String(32), index=True)


class TaskResult(Base, CreatedAtMixin):
    """催收结果明细（支持同一任务多次跟进）。"""

    __tablename__ = "task_results"

    id: Mapped[int] = mapped_column(_PK_BIGINT, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        _FK_BIGINT, ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    collector_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True
    )
    result: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    talk_used: Mapped[str | None] = mapped_column(Text)
