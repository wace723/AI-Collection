"""用户管理路由（supervisor 增强需求）。

GET   /api/users          —— 用户列表（SUPERVISOR/ADMIN）
POST  /api/users          —— 新增用户（ADMIN）
PUT   /api/users/{id}     —— 改角色/停用启用/重置密码（ADMIN）
DELETE /api/users/{id}    —— 删除用户（ADMIN；不可删自己、不可删最后一名 ADMIN）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user, require_role
from app.core.security import hash_password
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.user import UserCreateIn, UserOut, UserUpdateIn

router = APIRouter()

# 重置密码的默认值
_DEFAULT_PASSWORD = "admin123"


@router.get("", response_model=APIResponse[list[UserOut]])
def list_users(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("SUPERVISOR", "ADMIN")),
) -> APIResponse[list[UserOut]]:
    """用户列表（SUPERVISOR/ADMIN）。按 id 升序。"""
    users = db.query(User).order_by(User.id).all()
    return APIResponse(data=[UserOut.model_validate(u) for u in users])


@router.post("", response_model=APIResponse[UserOut], status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateIn,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[UserOut]:
    """新增用户（仅 ADMIN）。username 唯一。"""
    existing = (
        db.query(User).filter(User.username == payload.username).first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"用户名 {payload.username} 已存在",
        )
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        role=payload.role.value,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return APIResponse(data=UserOut.model_validate(user))


@router.put("/{user_id}", response_model=APIResponse[UserOut])
def update_user(
    user_id: int,
    payload: UserUpdateIn,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[UserOut]:
    """编辑用户（仅 ADMIN）：改角色 / 停用启用 / 重置密码为 admin123。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"用户 {user_id} 不存在"
        )

    if payload.role is not None:
        user.role = payload.role.value
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.reset_password:
        user.password_hash = hash_password(_DEFAULT_PASSWORD)

    db.commit()
    db.refresh(user)
    return APIResponse(data=UserOut.model_validate(user))


@router.delete("/{user_id}", response_model=APIResponse[dict])
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
) -> APIResponse[dict]:
    """删除用户（仅 ADMIN）。不可删自己；不可删最后一名 ADMIN。"""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="不可删除当前登录账号"
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"用户 {user_id} 不存在"
        )

    # 删除最后一个 ADMIN 会失去系统管理能力
    if user.role == "ADMIN":
        admin_count = db.query(User).filter(User.role == "ADMIN", User.is_active.is_(True)).count()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="系统至少保留一名管理员，不可删除",
            )

    db.delete(user)
    db.commit()
    return APIResponse(data={"deleted": user_id})
