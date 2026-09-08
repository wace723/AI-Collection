"""风险档配置与催收时点配置（版本化）。"""

from sqlalchemy import Boolean, DECIMAL, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RiskConfig(Base, TimestampMixin):
    """风险档阈值配置（版本化，is_active 标记当前生效）。"""

    __tablename__ = "risk_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer)
    high_threshold: Mapped[float] = mapped_column(DECIMAL(5, 2), default=70)
    medium_threshold: Mapped[float] = mapped_column(DECIMAL(5, 2), default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer)


class CollectionSchedule(Base):
    """每档催收时点配置：风险档 × 第 N 天 × 场景。"""

    __tablename__ = "collection_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    risk_config_id: Mapped[int] = mapped_column(
        ForeignKey("risk_configs.id", ondelete="CASCADE"), index=True
    )
    # HIGH / MEDIUM / LOW
    risk_tier: Mapped[str] = mapped_column(String(8), index=True)
    day_offset: Mapped[int] = mapped_column(Integer)
    # FIRST / SECOND / THIRD / DISPUTE / PROMISE
    scene: Mapped[str] = mapped_column(String(16))
    seq: Mapped[int] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
