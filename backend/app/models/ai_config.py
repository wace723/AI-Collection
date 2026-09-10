"""AI 话术配置（talk-002）。

单行配置表（id 固定为 1）：主管可在前端配置 api_key/base_url/model/provider/enabled。
DB 无记录时回退到 .env（settings）默认值。
"""

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AIConfig(Base, TimestampMixin):
    """AI 话术运行时配置（单行，id=1）。"""

    __tablename__ = "ai_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    # mock | openai_compatible
    provider: Mapped[str] = mapped_column(String(32), default="mock")
    api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
