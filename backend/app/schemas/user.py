"""用户管理 schema（supervisor 增强需求）。

与 auth.py 的 UserOut 区分：本模块用于用户 CRUD 的入参/出参。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import RoleEnum


class UserOut(BaseModel):
    """用户输出（含 id/角色/状态）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: RoleEnum
    is_active: bool


class UserCreateIn(BaseModel):
    """新增用户入参。"""

    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(min_length=1, max_length=64)
    role: RoleEnum


class UserUpdateIn(BaseModel):
    """编辑用户入参。全部可选，只更新提供字段。

    reset_password=True 时把密码重置为默认值 admin123。
    """

    role: RoleEnum | None = None
    is_active: bool | None = None
    reset_password: bool = False


__all__ = ["UserOut", "UserCreateIn", "UserUpdateIn"]
