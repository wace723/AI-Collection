"""聚合所有子路由。

业务路由（data/config/tasks/talk/dashboard）在各 feature 实现时挂到这里。
infra-001 仅挂 health（/health 不走 /api 前缀，见 main.py）。
"""

from fastapi import APIRouter

api_router = APIRouter()

# 各 feature 挂载点示例（infra-001 暂不实现）：
# from app.api import data, config, tasks, talk, dashboard
# api_router.include_router(data.router, prefix="/data", tags=["data"])
