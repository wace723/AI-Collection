"""FastAPI 应用入口。"""

import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.router import api_router
from app.core.config import settings
from app.core.database import SessionLocal
from app.scheduler import build_scheduler

logger = logging.getLogger(__name__)


def _run_startup_batch() -> None:
    """系统启动时自动跑批（data-004）：同步停机期间到期的催收时点。

    跑批失败不阻断启动（记录日志）；跑批幂等，重复触发不产生重复任务。
    """
    try:
        from app.services.task_engine import BatchNotReadyError, run_batch

        db = SessionLocal()
        try:
            run_batch(db, today=date.today(), recalc_risk=False)
        finally:
            db.close()
    except BatchNotReadyError:
        # 无生效风险档配置时跳过（待配置就绪后定时/导入触发）
        pass
    except Exception:
        logger.exception("启动跑批失败（不阻断启动）")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期：启动/关闭 APScheduler 每日跑批（task-001）。

    data-004：启动时自动跑批同步任务状态（停机期间到期时点）。
    测试（TestClient 未以 context manager 进入）不触发，后台线程不启动。
    """
    scheduler = build_scheduler()
    scheduler.start()
    _run_startup_batch()
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
