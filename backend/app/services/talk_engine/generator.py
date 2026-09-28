"""AI 话术生成编排（talk-002 → talk-003 模板化）。

流程（docs/02 §4.3）：取生效配置 → 匹配 AI_PROMPT 模板（无则降级内置默认 prompt）
→ 渲染 system/user prompt（合规基线追加后台 system）→ 调 LLMProvider → 写 AIConversation。
设计约束 #2：LLM 失败必须降级到模板话术，不阻断催收。
talk-003 D7：后台 AI system prompt 为追加而非覆盖合规基线；is_compliant 永不可关。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.models.order import Order, OrderFeature
from app.models.talk import AIConversation
from app.models.task import Task
from app.services.talk_engine.ai_config_service import get_effective_ai_config
from app.services.talk_engine.llm_provider import get_llm_provider
from app.services.talk_engine.matcher import match_templates
from app.services.talk_engine.renderer import build_values, render
from app.services.talk_engine.recommend import recommend_talks

logger = logging.getLogger(__name__)

# 合规基线（D7）：所有 AI system prompt 前置拼接，不可被后台配置覆盖。
# talk-002 原 build_prompt 的合规约束部分，提取为模块级常量供复用。
_COMPLIANCE_BASELINE = (
    "你是平台使用费催收助手。请基于以下信息生成专业、合规的催收话术："
    "有礼有节，明确告知缴费义务与逾期影响，给出具体缴费指引。"
    "不使用威胁、辱骂或虚假承诺。"
)

# 合规校验：LLM 输出不可预测，合规基线是第一道防线（system prompt 约束），
# 这里是第二道（输出层）纵深防线（技能原则6 + docs/03 TC-TALK-10）。
# 命中任一关键词 → 判定不合规 → 降级模板。关键词按业务可扩展。
_VIOLATION_KEYWORDS = (
    "辱骂", "威胁", "恐吓", "保证还款", "必定追回", "承诺免息",
    "免息", "承诺退款", "fuck", "shit", "damn",
)


def is_compliant(content: str) -> bool:
    """轻量合规校验：不含威胁/辱骂/虚假承诺类关键词。

    D7：此校验永远启用，不可通过任何配置关闭。
    """
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


def _default_prompts(task: Task, order: Order | None, feature: OrderFeature | None) -> tuple[str, str]:
    """内置默认 system/user prompt（无 AI_PROMPT 模板时降级用，保证 AI 链路不断）。"""
    system = _COMPLIANCE_BASELINE
    lines = [
        f"供应商：{order.supplier_name if order else '未知'}",
        f"订单号：{order.service_fee_order_no if order else '未知'}",
        f"风险档：{task.risk_tier}",
        f"场景：{task.scene}",
        f"应催日：{task.due_date}",
    ]
    if feature:
        lines.append(
            f"用户特征：历史中标率 {feature.win_rate}，会员 {feature.is_member_at_win}"
        )
    return system, "\n".join(lines)


def build_prompt(
    db: Session,
    task: Task,
    order: Order | None,
    feature: OrderFeature | None,
    *,
    today: date | None = None,
) -> tuple[str, str]:
    """组装 system / user prompt（talk-003：优先用 AI_PROMPT 模板，无则降级默认）。

    - 命中 AI_PROMPT 模板：渲染 system_prompt + user_prompt，system = 合规基线 + 后台 system
    - 无 AI_PROMPT 模板：降级内置默认 prompt（合规基线 system + 默认 user）
    """
    today = today or date.today()
    ai_templates = match_templates(db, task, template_type="AI_PROMPT")

    if not ai_templates:
        return _default_prompts(task, order, feature)

    tmpl = ai_templates[0]
    # system = 合规基线 + 后台 system_prompt（追加非覆盖，D7）
    admin_system = render(tmpl.system_prompt or "", task=task, order=order, feature=feature, today=today)
    system = f"{_COMPLIANCE_BASELINE}\n{admin_system}" if admin_system.strip() else _COMPLIANCE_BASELINE
    user_prompt = render(tmpl.user_prompt or "", task=task, order=order, feature=feature, today=today)
    return system, user_prompt


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

    system, user_prompt = build_prompt(db, task, order, feature)
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

    # 第二道防线：输出合规校验（TC-TALK-10，D7 永不可关）。不通过则降级模板，
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
