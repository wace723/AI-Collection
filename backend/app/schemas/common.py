"""通用响应包装与分页 schema。"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """统一 API 响应封装。"""

    success: bool = True
    data: T | None = None
    error: str | None = None


class Pagination(BaseModel):
    """分页元信息。"""

    total: int
    page: int
    limit: int


class PagedResponse(BaseModel, Generic[T]):
    """分页列表响应。"""

    items: list[T]
    total: int
    page: int
    limit: int
