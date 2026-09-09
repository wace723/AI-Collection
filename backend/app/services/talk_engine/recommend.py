"""话术推荐编排：取任务/订单/特征 → 匹配模板 → 渲染变量。

AI 生成（talk-002）后续在此追加 LLM 增强分支。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.models.order import Order, OrderFeature
from app.models.task import Task
from app.services.talk_engine.matcher import derive_user_tag, map_age_bucket, match_templates
from app.services.talk_engine.renderer import render


@dataclass(frozen=True)
class RecommendedTalk:
    """一条推荐话术（含渲染后内容）。"""

    template_id: int
    name: str
    risk_tier: str
    age_bucket: str
    scene: str
    user_feature_tag: str | None
    content: str  # 已渲染
    score: int


def recommend_talks(
    db: Session,
    task: Task,
    *,
    today: date | None = None,
) -> list[RecommendedTalk]:
    """为指定任务推荐话术（按匹配优先级排序）。

    Args:
        task: 任务（已含 order_id / risk_tier / scene）
        today: 账龄基准日，默认 date.today()
    """
    today = today or date.today()
    order = db.get(Order, task.order_id)
    feature = db.get(OrderFeature, task.order_id)
    age = (
        (today - order.win_bid_date).days if order and order.win_bid_date else 0
    )

    matched = match_templates(db, task, order, feature, today=today)
    # 重新计算 score 以便返回（match_templates 内部已排序，这里复算用于展示）
    return [
        RecommendedTalk(
            template_id=t.id,
            name=t.name,
            risk_tier=t.risk_tier,
            age_bucket=t.age_bucket,
            scene=t.scene,
            user_feature_tag=t.user_feature_tag,
            content=render(t.content, task=task, order=order, feature=feature),
            score=_score(t, task, age, feature),
        )
        for t in matched
    ]


def _score(t, task: Task, age: int, feature: OrderFeature | None) -> int:
    """复算匹配分（与 matcher._score_dim 同语义，用于展示排序依据）。"""
    age_bucket = map_age_bucket(age)
    user_tag = derive_user_tag(feature)

    def dim(tval: str, target: str) -> int:
        if tval == target:
            return 2
        if tval == "ANY":
            return 1
        return 0

    s_tag = 2 if (t.user_feature_tag == user_tag and user_tag is not None) else 1
    return (
        dim(t.risk_tier, task.risk_tier)
        + dim(t.age_bucket, age_bucket)
        + dim(t.scene, task.scene)
        + s_tag
    )


__all__ = ["RecommendedTalk", "recommend_talks"]
