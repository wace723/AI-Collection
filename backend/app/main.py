"""FastAPI 应用入口。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.router import api_router
from app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/docs",
    openapi_url="/openapi.json",
    version="0.1.0",
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

# APScheduler 跑批初始化留给 task-001，此处置空。
