"""安全相关：JWT 与密码哈希。

infra-001 仅放函数签名占位，实现留给 infra-002。
"""

from datetime import datetime


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """生成 JWT。infra-002 实现。"""
    raise NotImplementedError("JWT 实现于 infra-002")


def decode_access_token(token: str) -> str | None:
    """解析 JWT，返回 subject。infra-002 实现。"""
    raise NotImplementedError("JWT 实现于 infra-002")


def hash_password(raw: str) -> str:
    """密码哈希。infra-002 实现。"""
    raise NotImplementedError("密码哈希实现于 infra-002")


def verify_password(raw: str, hashed: str) -> bool:
    """校验密码。infra-002 实现。"""
    raise NotImplementedError("密码校验实现于 infra-002")
