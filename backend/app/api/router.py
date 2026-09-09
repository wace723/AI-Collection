"""聚合所有子路由。"""

from fastapi import APIRouter

from app.api import auth

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# 各 feature 挂载点示例（后续实现）：
# from app.api import data, config, tasks, talk, dashboard
# api_router.include_router(data.router, prefix="/data", tags=["data"])
