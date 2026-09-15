"""聚合所有子路由。"""

from fastapi import APIRouter

from app.api import auth, config, dashboard, data, supervisor, talk, tasks, users

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(data.router, prefix="/data", tags=["data"])
api_router.include_router(config.router, prefix="/config", tags=["config"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(talk.router, prefix="/talk", tags=["talk"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(supervisor.router, prefix="/supervisor", tags=["supervisor"])
