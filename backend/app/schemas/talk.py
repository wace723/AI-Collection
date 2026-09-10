"""话术相关 schema（talk-001/002）。"""

from __future__ import annotations

from typing import Literal

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


class GenerateTalkOut(BaseModel):
    """AI 话术生成响应。"""

    enabled: bool
    content: str | None
    conversation_id: int | None
    provider: str
    fallback: bool
    fallback_reason: str | None = None


class FeedbackIn(BaseModel):
    """话术反馈入参。"""

    conversation_id: int
    feedback: Literal["useful", "useless"]


class FeedbackOut(BaseModel):
    """话术反馈响应。"""

    conversation_id: int
    feedback: str


__all__ = [
    "TalkTemplateOut",
    "TalkRecommendOut",
    "GenerateTalkOut",
    "FeedbackIn",
    "FeedbackOut",
]
