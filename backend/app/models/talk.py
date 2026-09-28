"""话术模板与 AI 话术记录。"""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class TalkTemplate(Base):
    """话术模板：按 [风险档 × 轮次] 二维匹配（talk-003 重构）。

    scene 取值 ROUND_N（N 为该档 schedules 的 seq，由 config_service 自动生成）。
    账龄段/用户特征不再参与匹配，仅作存档（D1 决策）；其值经 renderer 填充为话术变量。
    """

    __tablename__ = "talk_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    # HIGH / MEDIUM / LOW
    risk_tier: Mapped[str] = mapped_column(String(8), index=True)
    # 账龄段（0_7/8_15/.../90_PLUS）——不再参与匹配，仅作存档；话术变量经 renderer 取账龄值
    age_bucket: Mapped[str] = mapped_column(String(16), default="ANY")
    # ROUND_N（N 为该档 schedules seq）；不再用 FIRST/SECOND/THIRD 固定枚举
    scene: Mapped[str] = mapped_column(String(16), index=True)
    # 用户特征标签——不再参与匹配，仅作存档
    user_feature_tag: Mapped[str | None] = mapped_column(String(32))
    # FIXED（固定模板，用 content）/ AI_PROMPT（AI 提示词，用 system_prompt+user_prompt）
    template_type: Mapped[str] = mapped_column(
        String(16), default="FIXED", nullable=False, index=True
    )
    # FIXED 模板：渲染后直接展示的最终文本
    content: Mapped[str] = mapped_column(Text)
    # AI_PROMPT 模板：渲染后喂 LLM 的 system / user prompt（FIXED 行为 NULL）
    system_prompt: Mapped[str | None] = mapped_column(Text)
    user_prompt: Mapped[str | None] = mapped_column(Text)
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
