"""话术推荐编排：取任务/订单/特征 → 二维匹配模板 → 渲染变量（talk-003 重构）。

匹配键 [风险档 × 轮次]，无兜底；未配返回空列表。recommend_talks 默认返回 FIXED
模板（工作台主推话术）；AI_PROMPT 模板由 generator 单独取。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.models.order import Order, OrderFeature
from app.models.task import Task
from app.services.talk_engine.matcher import match_templates
from app.services.talk_engine.renderer import render


@dataclass(frozen=True)
class RecommendedTalk:
    """一条推荐话术（含渲染后内容）。"""

    template_id: int
    name: str
    risk_tier: str
    scene: str
    template_type: str
    content: str  # FIXED 已渲染；AI_PROMPT 为空（由 generator 处理 prompt）


def recommend_talks(
    db: Session,
    task: Task,
    *,
    template_type: str = "FIXED",
    today: date | None = None,
) -> list[RecommendedTalk]:
    """为指定任务推荐话术（二维匹配，未配返回空列表）。

    Args:
        task: 任务（已含 risk_tier / scene）
        template_type: FIXED（默认，工作台主推）/ AI_PROMPT
        today: 渲染账龄基准日，默认 date.today()
    """
    today = today or date.today()
    order = db.get(Order, task.order_id)
    feature = db.get(OrderFeature, task.order_id)

    matched = match_templates(db, task, template_type=template_type)
    return [
        RecommendedTalk(
            template_id=t.id,
            name=t.name,
            risk_tier=t.risk_tier,
            scene=t.scene,
            template_type=t.template_type,
            content=(
                render(t.content, task=task, order=order, feature=feature, today=today)
                if template_type == "FIXED"
                else ""
            ),
        )
        for t in matched
    ]


__all__ = ["RecommendedTalk", "recommend_talks"]
