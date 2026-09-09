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
from app.schemas.config import RiskConfigOut, RiskConfigUpdateIn
from app.services.risk_engine.config_service import (
    AlreadyActiveError,
    ConfigNotFoundError,
    ConfigSnapshot,
    get_config_history,
    get_current_config,
    rollback_to_version,
    update_config,
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
