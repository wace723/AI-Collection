"""认证相关 schema。"""

from enum import Enum

from pydantic import BaseModel


class RoleEnum(str, Enum):
    COLLECTOR = "COLLECTOR"
    SUPERVISOR = "SUPERVISOR"
    ADMIN = "ADMIN"


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: RoleEnum
    is_active: bool


class LoginData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
