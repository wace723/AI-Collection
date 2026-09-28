"""talk_engine：话术模板匹配与变量渲染（talk-001 → talk-003 二维重构）。

对外稳定入口：
- match_templates：按 [风险档 × 轮次] 二维精确匹配（无兜底，talk-003）
- recommend_talks：编排匹配+渲染，返回推荐话术列表（未配返回空）
- map_age_bucket / derive_user_tag / render / build_values：原语与变量取值
- validate_placeholders / available_placeholders：占位符校验与列表
- compute_coverage / diff_coverage：覆盖度矩阵与联动校验
AI 生成（talk-002 → talk-003）：generator 读 AI_PROMPT 模板 + 合规基线追加。
"""

from app.services.talk_engine.ai_config_service import (
    EffectiveAIConfig,
    get_ai_config_row,
    get_effective_ai_config,
    mask_api_key,
    update_ai_config,
)
from app.services.talk_engine.coverage import (
    CoverageCell,
    CoverageHint,
    CoverageMatrix,
    compute_coverage,
    diff_coverage,
    hint_to_dict,
)
from app.services.talk_engine.generator import GenerateTalkResult, generate_talk
from app.services.talk_engine.matcher import (
    AGE_BUCKETS,
    derive_user_tag,
    map_age_bucket,
    match_templates,
)
from app.services.talk_engine.placeholders import (
    PlaceholderInfo,
    available_placeholders,
    validate_placeholders,
)
from app.services.talk_engine.recommend import RecommendedTalk, recommend_talks
from app.services.talk_engine.renderer import build_values, render

__all__ = [
    "AGE_BUCKETS",
    "map_age_bucket",
    "derive_user_tag",
    "match_templates",
    "render",
    "build_values",
    "RecommendedTalk",
    "recommend_talks",
    "EffectiveAIConfig",
    "get_ai_config_row",
    "get_effective_ai_config",
    "mask_api_key",
    "update_ai_config",
    "GenerateTalkResult",
    "generate_talk",
    "PlaceholderInfo",
    "validate_placeholders",
    "available_placeholders",
    "CoverageCell",
    "CoverageHint",
    "CoverageMatrix",
    "compute_coverage",
    "diff_coverage",
    "hint_to_dict",
]
