"""/health 端点。"""

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """根路径健康检查（无需鉴权）。"""
    return HealthResponse(status="ok", app=settings.APP_NAME, version="0.1.0")


@router.get("/api/health", response_model=HealthResponse)
def api_health() -> HealthResponse:
    """带 /api 前缀的健康检查，供前端经 vite proxy 访问。"""
    return HealthResponse(status="ok", app=settings.APP_NAME, version="0.1.0")

