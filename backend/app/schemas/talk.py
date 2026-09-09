"""话术相关 schema（talk-001）。"""

from __future__ import annotations

from pydantic import BaseModel


class TalkTemplateOut(BaseModel):
    """推荐话术项（content 已渲染）。"""

    template_id: int
    name: str
    risk_tier: str
    age_bucket: str
    scene: str
    user_feature_tag: str | None = None
    content: str
    score: int


class TalkRecommendOut(BaseModel):
    """推荐话术响应。"""

    task_id: int
    age_bucket: str
    user_tag: str | None
    templates: list[TalkTemplateOut]


__all__ = ["TalkTemplateOut", "TalkRecommendOut"]
