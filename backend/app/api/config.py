"""risk-002 风险档配置路由。

GET /risk/current  —— 当前生效配置（登录可见，无配置 404）
PUT /risk          —— 更新阈值+催收时点，生成新版本（ADMIN）
GET /risk/history  —— 配置历史（ADMIN）
POST /risk/rollback/{version} —— 回滚到指定版本（ADMIN，方案 B 复制为新版本）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_role
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.config import (
    AIConfigOut,
    AIConfigUpdateIn,
    RiskConfigOut,
    RiskConfigUpdateIn,
)
from app.services.risk_engine.config_service import (
    AlreadyActiveError,
    ConfigNotFoundError,
    ConfigSnapshot,
    get_config_history,
    get_current_config,
    rollback_to_version,
    update_config,
)
from app.services.talk_engine.ai_config_service import (
    get_ai_config_row,
    get_effective_ai_config,
    mask_api_key,
    update_ai_config,
)

router = APIRouter()


def _to_out(snap: ConfigSnapshot) -> RiskConfigOut:
    """ConfigSnapshot → RiskConfigOut（不可变转换，不 mutate ORM 实例）。"""
    cfg = snap.config
    return RiskConfigOut(
        id=cfg.id,
        version=cfg.version,
        high_threshold=float(cfg.high_threshold),
        medium_threshold=float(cfg.medium_threshold),
        is_active=cfg.is_active,
        created_by=cfg.created_by,
        created_at=cfg.created_at,
        updated_at=cfg.updated_at,
        schedules=[
            {
                "risk_tier": s.risk_tier,
                "day_offset": s.day_offset,
                "scene": s.scene,
                "seq": s.seq,
                "is_active": s.is_active,
            }
            for s in snap.schedules
        ],
    )


@router.get("/risk/current", response_model=APIResponse[RiskConfigOut])
def get_current(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> APIResponse[RiskConfigOut]:
    """当前生效配置。"""
    snap = get_current_config(db)
    if snap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="尚无生效配置，请先运行 seed 初始化",
        )
    return APIResponse(data=_to_out(snap))


@router.put("/risk", response_model=APIResponse[RiskConfigOut])
def update_risk(
    payload: RiskConfigUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[RiskConfigOut]:
    """更新阈值+催收时点，生成新版本（仅 ADMIN）。"""
    snap = update_config(db, payload, created_by=current_user.id)
    return APIResponse(data=_to_out(snap))


@router.get("/risk/history", response_model=APIResponse[list[RiskConfigOut]])
def get_history(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[list[RiskConfigOut]]:
    """配置历史（仅 ADMIN）。"""
    snaps = get_config_history(db)
    return APIResponse(data=[_to_out(s) for s in snaps])


@router.post(
    "/risk/rollback/{version}", response_model=APIResponse[RiskConfigOut]
)
def rollback(
    version: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[RiskConfigOut]:
    """回滚到指定历史版本（仅 ADMIN）。

    方案 B：复制目标版本阈值+schedules 为新版本，旧记录永不被改。
    """
    try:
        snap = rollback_to_version(db, version, created_by=current_user.id)
    except ConfigNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except AlreadyActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return APIResponse(data=_to_out(snap))


# ── AI 话术配置（talk-002） ────────────────────────────────────────


@router.get("/ai", response_model=APIResponse[AIConfigOut])
def get_ai(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("SUPERVISOR", "ADMIN")),
) -> APIResponse[AIConfigOut]:
    """当前生效的 AI 话术配置（api_key 脱敏，主管/管理员可查）。"""
    row = get_ai_config_row(db)
    eff = get_effective_ai_config(db)
    return APIResponse(
        data=AIConfigOut(
            provider=eff.provider,
            api_key_masked=mask_api_key(eff.api_key),
            base_url=eff.base_url,
            model=eff.model,
            enabled=eff.enabled,
            from_db=eff.from_db,
            updated_at=row.updated_at if row else None,
            updated_by=row.updated_by if row else None,
        )
    )


@router.put("/ai", response_model=APIResponse[AIConfigOut])
def update_ai(
    payload: AIConfigUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("SUPERVISOR", "ADMIN")),
) -> APIResponse[AIConfigOut]:
    """更新 AI 话术配置（主管/管理员）。api_key 空则保留旧值。"""
    row = update_ai_config(db, payload, current_user)
    eff = get_effective_ai_config(db)
    return APIResponse(
        data=AIConfigOut(
            provider=eff.provider,
            api_key_masked=mask_api_key(eff.api_key),
            base_url=eff.base_url,
            model=eff.model,
            enabled=eff.enabled,
            from_db=True,
            updated_at=row.updated_at,
            updated_by=row.updated_by,
        )
    )
