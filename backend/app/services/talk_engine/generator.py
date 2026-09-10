"""AI 话术生成编排（talk-002）。

流程（docs/02 §4.3）：取生效配置 → 构造 prompt → 调 LLMProvider → 写 AIConversation。
设计约束 #2：LLM 失败必须降级到模板话术，不阻断催收。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.order import Order, OrderFeature
from app.models.talk import AIConversation
from app.models.task import Task
from app.services.talk_engine.ai_config_service import get_effective_ai_config
from app.services.talk_engine.llm_provider import get_llm_provider
from app.services.talk_engine.recommend import recommend_talks

logger = logging.getLogger(__name__)

# 合规校验：LLM 输出不可预测，system prompt 约束是第一道防线，
# 这里是第二道（输出层）纵深防线（技能原则6 + docs/03 TC-TALK-10）。
# 命中任一关键词 → 判定不合规 → 降级模板。关键词按业务可扩展。
_VIOLATION_KEYWORDS = (
    "辱骂", "威胁", "恐吓", "保证还款", "必定追回", "承诺免息",
    "免息", "承诺退款", "fuck", "shit", "damn",
)


def is_compliant(content: str) -> bool:
    """轻量合规校验：不含威胁/辱骂/虚假承诺类关键词。"""
    lower = content.lower()
    return not any(kw.lower() in lower for kw in _VIOLATION_KEYWORDS)


@dataclass(frozen=True)
class GenerateTalkResult:
    """AI 话术生成结果。"""

    enabled: bool
    content: str | None
    conversation_id: int | None
    provider: str
    fallback: bool = False
    fallback_reason: str | None = None


def build_prompt(
    task: Task,
    order: Order | None,
    feature: OrderFeature | None,
    template_hint: str | None,
) -> tuple[str, str]:
    """组装 system / user prompt（参考 docs/02 §4.3.3）。"""
    system = (
        "你是平台使用费催收助手。请基于以下信息生成专业、合规的催收话术："
        "有礼有节，明确告知缴费义务与逾期影响，给出具体缴费指引。"
        "不使用威胁、辱骂或虚假承诺。"
    )
    lines = [
        f"供应商：{order.supplier_name if order else '未知'}",
        f"订单号：{order.service_fee_order_no if order else '未知'}",
        f"风险档：{task.risk_tier}",
        f"场景：{task.scene}",
        f"应催日：{task.due_date}",
    ]
    if feature:
        lines.append(
            f"用户特征：历史中标率 {feature.win_rate}，"
            f"会员 {feature.is_member_at_win}"
        )
    if template_hint:
        lines.append(f"参考模板风格：{template_hint}")
    return system, "\n".join(lines)


def generate_talk(db: Session, task: Task) -> GenerateTalkResult:
    """为任务生成 AI 话术。失败降级模板（设计约束 #2）。"""
    eff = get_effective_ai_config(db)

    order = db.get(Order, task.order_id)
    feature = db.get(OrderFeature, task.order_id)
    recs = recommend_talks(db, task)
    template_hint = recs[0].content if recs else None

    # 开关关闭：仅返回模板话术（TC-TALK-07）
    if not eff.enabled:
        return GenerateTalkResult(
            enabled=False,
            content=template_hint or "（AI 话术已关闭，且无匹配模板）",
            conversation_id=None,
            provider=eff.provider,
            fallback=True,
            fallback_reason="AI 话术已关闭，返回模板话术",
        )

    system, user_prompt = build_prompt(task, order, feature, template_hint)
    provider = get_llm_provider(eff)

    try:
        content = provider.generate(system, user_prompt)
    except Exception:
        logger.exception("LLM 生成失败，降级模板话术（task_id=%s）", task.id)
        conv = AIConversation(
            task_id=task.id,
            order_id=task.order_id,
            prompt=user_prompt,
            response="",
            provider=eff.provider,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return GenerateTalkResult(
            enabled=True,
            content=template_hint or "（LLM 失败且无模板）",
            conversation_id=conv.id,
            provider=eff.provider,
            fallback=True,
            fallback_reason="LLM 调用失败，已降级模板",
        )

    # 第二道防线：输出合规校验（TC-TALK-10）。不通过则降级模板，
    # 但仍记录原始 LLM 输出到 AIConversation 以便审计。
    if not is_compliant(content):
        logger.warning(
            "LLM 话术合规检查未通过，降级模板（task_id=%s）", task.id
        )
        conv = AIConversation(
            task_id=task.id,
            order_id=task.order_id,
            prompt=user_prompt,
            response=content,
            provider=eff.provider,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return GenerateTalkResult(
            enabled=True,
            content=template_hint or "（合规降级且无模板）",
            conversation_id=conv.id,
            provider=eff.provider,
            fallback=True,
            fallback_reason="AI 话术合规检查未通过，已降级模板",
        )

    conv = AIConversation(
        task_id=task.id,
        order_id=task.order_id,
        prompt=user_prompt,
        response=content,
        provider=eff.provider,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return GenerateTalkResult(
        enabled=True,
        content=content,
        conversation_id=conv.id,
        provider=eff.provider,
        fallback=False,
    )


def update_feedback(
    db: Session, conversation_id: int, feedback: str
) -> AIConversation:
    """更新 AI 话术反馈（useful/useless，TC-TALK-09）。"""
    conv = db.get(AIConversation, conversation_id)
    if conv is None:
        raise LookupError(f"会话 {conversation_id} 不存在")
    conv.feedback = feedback
    db.commit()
    return conv


__all__ = [
    "GenerateTalkResult",
    "build_prompt",
    "generate_talk",
    "update_feedback",
]
