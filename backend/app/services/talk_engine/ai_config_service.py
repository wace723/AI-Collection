"""talk-002 AI 话术配置服务。

策略：DB 单行配置（id=1）优先；DB 无记录时回退 .env（settings）默认值。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_config import AIConfig
from app.models.user import User
from app.schemas.config import AIConfigUpdateIn

# 单行配置固定主键
_SINGLETON_ID = 1


@dataclass(frozen=True)
class EffectiveAIConfig:
    """生效中的 AI 配置（DB 优先，回退 .env）。"""

    provider: str
    api_key: str | None
    base_url: str | None
    model: str | None
    enabled: bool
    from_db: bool  # 是否来自 DB（True）还是 .env 回退（False）


def mask_api_key(key: str | None) -> str | None:
    """脱敏显示 api_key（如 tqsk***4ed1）。"""
    if not key:
        return None
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}***{key[-4:]}"


def get_ai_config_row(db: Session) -> AIConfig | None:
    """取 DB 单行配置（id=1）。"""
    return db.get(AIConfig, _SINGLETON_ID)


def get_effective_ai_config(db: Session) -> EffectiveAIConfig:
    """生效配置：DB 优先，无则回退 .env。"""
    row = get_ai_config_row(db)
    if row is not None:
        return EffectiveAIConfig(
            provider=row.provider,
            api_key=row.api_key,
            base_url=row.base_url,
            model=row.model,
            enabled=row.enabled,
            from_db=True,
        )
    return EffectiveAIConfig(
        provider=settings.LLM_PROVIDER,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        enabled=settings.AI_TALK_ENABLED,
        from_db=False,
    )


def update_ai_config(db: Session, payload: AIConfigUpdateIn, user: User) -> AIConfig:
    """更新（或首次创建）AI 配置单行。

    api_key 传 None/空字符串时保留旧值（前端脱敏展示后不回填明文）。
    """
    row = get_ai_config_row(db)
    if row is None:
        row = AIConfig(
            id=_SINGLETON_ID,
            provider=payload.provider,
            api_key=payload.api_key or None,
            base_url=payload.base_url or None,
            model=payload.model or None,
            enabled=payload.enabled,
            updated_by=user.id,
        )
        db.add(row)
    else:
        row.provider = payload.provider
        if payload.api_key:  # 非空才覆盖（避免脱敏回填清空 key）
            row.api_key = payload.api_key
        row.base_url = payload.base_url or None
        row.model = payload.model or None
        row.enabled = payload.enabled
        row.updated_by = user.id
    db.commit()
    db.refresh(row)
    return row


__all__ = [
    "EffectiveAIConfig",
    "mask_api_key",
    "get_ai_config_row",
    "get_effective_ai_config",
    "update_ai_config",
]
