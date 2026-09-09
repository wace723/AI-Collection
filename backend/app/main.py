"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.router import api_router
from app.core.config import settings
from app.scheduler import build_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期：启动/关闭 APScheduler 每日跑批（task-001）。

    测试（TestClient 未以 context manager 进入）不触发，后台线程不启动。
    """
    scheduler = build_scheduler()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/docs",
    openapi_url="/openapi.json",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS（开发期允许前端 5173）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# /health 挂在根（不属业务 API，无需鉴权）
app.include_router(health_router)

# 业务 API 统一前缀 /api
app.include_router(api_router, prefix="/api")
