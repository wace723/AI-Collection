"""话术模板匹配（talk-001 基础话术引擎）。

匹配维度（docs/02 §4.3.2）：
    [风险档 × 账龄段 × 场景 × 用户特征]
每个维度支持精确值或 ANY（通配，低分）。优先级：精确越多分越高，ANY 越多分越低。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models.order import Order, OrderFeature
from app.models.talk import TalkTemplate
from app.models.task import Task

# 账龄段枚举（与 TalkTemplate.age_bucket 一致）
AGE_BUCKETS = ("0_7", "8_15", "16_30", "31_90", "90_PLUS")
ANY = "ANY"


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
    """从用户特征推导话术匹配标签。MVP 只区分会员/非会员。

    后续可扩展 SMALL_FUND / VIP 等（docs/02 §4.3.2 user_feature_tag）。
    """
    if feature is None:
        return None
    if feature.is_member_at_win is True:
        return "MEMBER"
    return None


def _score_dim(template_val: str, target_val: str) -> int | None:
    """单维度打分：精确 2 / ANY 通配 1 / 不匹配 None（排除）。"""
    if template_val == target_val:
        return 2
    if template_val == ANY:
        return 1
    return None  # 硬不匹配 → 过滤


def match_templates(
    db: Session,
    task: Task,
    order: Order,
    feature: OrderFeature | None = None,
    *,
    today: date | None = None,
) -> list[TalkTemplate]:
    """返回按优先级排序的匹配模板（精确在前，ANY 兜底在后）。

    Args:
        task: 任务（取 risk_tier / scene）
        order: 订单（取 win_bid_date 计算账龄）
        feature: 用户特征（推导 user_tag）
        today: 基准日，默认 date.today()（测试注入）
    """
    today = today or date.today()
    age = (
        (today - order.win_bid_date).days
        if order.win_bid_date
        else 0
    )
    age_bucket = map_age_bucket(age)
    user_tag = derive_user_tag(feature)

    templates = (
        db.query(TalkTemplate).filter(TalkTemplate.is_active.is_(True)).all()
    )

    scored: list[tuple[int, TalkTemplate]] = []
    for t in templates:
        # user_feature_tag 维度：模板 None=通配；非 None 必须等于 user_tag
        if t.user_feature_tag is not None and t.user_feature_tag != user_tag:
            continue
        s_risk = _score_dim(t.risk_tier, task.risk_tier)
        s_age = _score_dim(t.age_bucket, age_bucket)
        s_scene = _score_dim(t.scene, task.scene)
        if s_risk is None or s_age is None or s_scene is None:
            continue  # 任一维度硬不匹配 → 排除
        # user_tag 维度：精确 2（t.tag==user_tag）/ 通配 1（t.tag is None）
        s_tag = 2 if t.user_feature_tag == user_tag and user_tag is not None else 1
        score = s_risk + s_age + s_scene + s_tag
        scored.append((score, t))

    # 总分降序，同分按 id 升序（稳定）
    scored.sort(key=lambda x: (-x[0], x[1].id))
    return [t for _, t in scored]


__all__ = [
    "AGE_BUCKETS",
    "ANY",
    "map_age_bucket",
    "derive_user_tag",
    "match_templates",
]
