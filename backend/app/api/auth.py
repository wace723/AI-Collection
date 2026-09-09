"""认证路由：登录 / 当前用户 / 角色权限验证。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_role
from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.schemas.auth import LoginData, LoginRequest, UserOut
from app.schemas.common import APIResponse

router = APIRouter()


@router.post("/login", response_model=APIResponse[LoginData])
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> APIResponse[LoginData]:
    """用户名密码登录，返回 JWT。"""
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被停用",
        )
    token = create_access_token(subject=user.username)
    return APIResponse(
        data=LoginData(
            access_token=token,
            user=UserOut.model_validate(user, from_attributes=True),
        )
    )


@router.get("/me", response_model=APIResponse[UserOut])
def me(current_user: User = Depends(get_current_user)) -> APIResponse[UserOut]:
    """返回当前登录用户信息。"""
    return APIResponse(data=UserOut.model_validate(current_user, from_attributes=True))


@router.get("/admin-only", response_model=APIResponse[dict])
def admin_only(current_user: User = Depends(require_role("ADMIN"))) -> APIResponse[dict]:
    """仅 ADMIN 可访问（用于验证 403）。"""
    return APIResponse(data={"message": "管理员通道", "role": current_user.role})


@router.get("/supervisor-or-admin", response_model=APIResponse[dict])
def supervisor_or_admin(
    current_user: User = Depends(require_role("SUPERVISOR", "ADMIN")),
) -> APIResponse[dict]:
    """SUPERVISOR 或 ADMIN 可访问。"""
    return APIResponse(data={"message": "主管通道", "role": current_user.role})
