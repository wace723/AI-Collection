"""话术相关 schema（talk-001/002/003）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TalkTemplateOut(BaseModel):
    """推荐话术项（别名 TalkTemplateItem，兼容旧引用）。"""

    template_id: int
    name: str
    risk_tier: str
    scene: str
    template_type: str
    content: str


# ── 推荐话术（工作台用，二维匹配结果） ──────────────────────────────


class TalkTemplateItem(BaseModel):
    """推荐话术项（FIXED 模板，content 已渲染；AI_PROMPT 由 generate 单独取）。"""

    template_id: int
    name: str
    risk_tier: str
    scene: str
    template_type: str
    content: str


class TalkRecommendOut(BaseModel):
    """推荐话术响应（talk-003：未配话术返回空列表 + has_talk=false）。"""

    task_id: int
    has_talk: bool  # True=有匹配 FIXED 模板；False=该轮次未配话术
    templates: list[TalkTemplateItem] = []


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


# ── 话术模板管理（talk-003 管理后台 CRUD） ──────────────────────────


class TalkTemplateIn(BaseModel):
    """创建/更新话术模板入参（ADMIN）。

    scene 必须为 ROUND_N 格式；template_type FIXED 用 content，AI_PROMPT 用
    system_prompt + user_prompt。占位符由后端校验（validate_placeholders）。
    """

    name: str = Field(min_length=1, max_length=128)
    risk_tier: Literal["HIGH", "MEDIUM", "LOW"]
    scene: str = Field(description="轮次标识 ROUND_N（如 ROUND_1）")
    template_type: Literal["FIXED", "AI_PROMPT"] = "FIXED"
    content: str | None = None  # FIXED 必填
    system_prompt: str | None = None  # AI_PROMPT 必填
    user_prompt: str | None = None  # AI_PROMPT 必填
    is_active: bool = True


class TalkTemplateManageOut(BaseModel):
    """话术模板管理输出（含所有字段）。"""

    id: int
    name: str
    risk_tier: str
    scene: str
    age_bucket: str | None = None  # 存档，不再参与匹配
    user_feature_tag: str | None = None  # 存档，不再参与匹配
    template_type: str
    content: str | None = None
    system_prompt: str | None = None
    user_prompt: str | None = None
    is_active: bool


class PlaceholderOut(BaseModel):
    """可用占位符（前端「插入变量」按钮展示）。"""

    key: str
    description: str
    group: str


# ── 覆盖度矩阵（talk-003 D6） ──────────────────────────────────────


class CoverageCellOut(BaseModel):
    """覆盖度矩阵一格。"""

    risk_tier: str
    scene: str
    day_offset: int
    fixed_configured: bool
    ai_prompt_configured: bool


class CoverageMatrixOut(BaseModel):
    """覆盖度矩阵响应。"""

    cells: list[CoverageCellOut]
    missing_count: int


class CoverageHintOut(BaseModel):
    """风险档配置变更的话术覆盖提示（嵌入 RiskConfigOut.coverage_hint）。"""

    added_rounds: list[dict]  # [{"risk_tier":..., "scene":...}]
    deleted_rounds: list[dict]
    missing_cells: list[dict]


__all__ = [
    "TalkTemplateItem",
    "TalkRecommendOut",
    "GenerateTalkOut",
    "FeedbackIn",
    "FeedbackOut",
    "TalkTemplateIn",
    "TalkTemplateManageOut",
    "PlaceholderOut",
    "CoverageCellOut",
    "CoverageMatrixOut",
    "CoverageHintOut",
]
