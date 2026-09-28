"""话术模板匹配（talk-001 基础 → talk-003 二维重构）。

匹配维度（talk-003 D1 收敛）：
    [风险档 × 轮次(scene)] 精确匹配，无 ANY 兜底。
账龄段、用户特征不再参与匹配，仅作话术变量（renderer 取值）。

按 template_type 过滤（FIXED / AI_PROMPT），调用方指定要哪类模板。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models.order import Order, OrderFeature
from app.models.talk import TalkTemplate
from app.models.task import Task

# 账龄段枚举（renderer 占位符取值用，不再参与匹配）
AGE_BUCKETS = ("0_7", "8_15", "16_30", "31_90", "90_PLUS")


def map_age_bucket(age: int) -> str:
    """账龄（天）→ 账龄段。

    边界（docs/03 TC-TALK-04）：
        0~7 → 0_7；8~15 → 8_15；16~30 → 16_30；31~90 → 31_90；91+ → 90_PLUS
    """
    if age < 0:
        age = 0
    if age <= 7:
        return "0_7"
    if age <= 15:
        return "8_15"
    if age <= 30:
        return "16_30"
    if age <= 90:
        return "31_90"
    return "90_PLUS"


def derive_user_tag(feature: OrderFeature | None) -> str | None:
    """从用户特征推导话术匹配标签（renderer 占位符取值用，不再参与匹配）。

    MVP 只区分会员/非会员。后续可扩展 SMALL_FUND / VIP 等。
    """
    if feature is None:
        return None
    if feature.is_member_at_win is True:
        return "MEMBER"
    return None


def match_templates(
    db: Session,
    task: Task,
    *,
    template_type: str = "FIXED",
) -> list[TalkTemplate]:
    """返回 [风险档 × scene] 精确匹配的模板（talk-003 二维匹配，无兜底）。

    Args:
        task: 任务（取 risk_tier / scene）
        template_type: FIXED / AI_PROMPT，指定要哪类模板
    Returns:
        匹配模板列表（按 is_active 过滤；同格多条时按 id 升序）。空列表 = 未配话术。
    """
    return (
        db.query(TalkTemplate)
        .filter(
            TalkTemplate.is_active.is_(True),
            TalkTemplate.template_type == template_type,
            TalkTemplate.risk_tier == task.risk_tier,
            TalkTemplate.scene == task.scene,
        )
        .order_by(TalkTemplate.id.asc())
        .all()
    )


__all__ = [
    "AGE_BUCKETS",
    "map_age_bucket",
    "derive_user_tag",
    "match_templates",
]
