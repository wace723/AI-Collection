"""talk_engine：话术模板匹配与变量渲染（talk-001）。

对外稳定入口：
- match_templates：按 [风险档×账龄段×场景×用户特征] 匹配
- recommend_talks：编排匹配+渲染，返回推荐话术列表
- map_age_bucket / derive_user_tag / render：原语
AI 生成（talk-002）后续追加 LLM Provider 分支。
"""

from app.services.talk_engine.matcher import (
    AGE_BUCKETS,
    ANY,
    derive_user_tag,
    map_age_bucket,
    match_templates,
)
from app.services.talk_engine.recommend import RecommendedTalk, recommend_talks
from app.services.talk_engine.renderer import render

__all__ = [
    "AGE_BUCKETS",
    "ANY",
    "map_age_bucket",
    "derive_user_tag",
    "match_templates",
    "render",
    "RecommendedTalk",
    "recommend_talks",
]
