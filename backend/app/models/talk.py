"""话术模板与 AI 话术记录。"""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class TalkTemplate(Base):
    """基础话术模板：按 [风险档 × 账龄段 × 场景 × 用户特征] 匹配。"""

    __tablename__ = "talk_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    # HIGH / MEDIUM / LOW / ANY
    risk_tier: Mapped[str] = mapped_column(String(8), index=True)
    # 0_7 / 8_15 / 16_30 / 31_90 / 90_PLUS / ANY
    age_bucket: Mapped[str] = mapped_column(String(16))
    # FIRST / SECOND / THIRD / DISPUTE / PROMISE
    scene: Mapped[str] = mapped_column(String(16))
    # VIP / MEMBER / SMALL_FUND / ...，可空
    user_feature_tag: Mapped[str | None] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AIConversation(Base, CreatedAtMixin):
    """AI 话术生成记录，用于复盘与反馈优化。"""

    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    prompt: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)
    # claude / openai / mock
    provider: Mapped[str] = mapped_column(String(16))
    # useful / useless
    feedback: Mapped[str | None] = mapped_column(String(16))
