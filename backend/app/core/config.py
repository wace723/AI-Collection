"""应用配置：基于 pydantic-settings，从环境变量 / .env 读取。"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# 后端目录（.env 与 dev.db 都相对此目录解析）
BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """全局配置。MVP 仅含必要项，LLM 相关为预留。"""

    # 应用
    APP_NAME: str = "平台使用费催收系统"
    DEBUG: bool = True
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # 数据库
    DATABASE_URL: str = "sqlite:///./dev.db"

    # JWT（infra-002 实现，此处预留）
    JWT_SECRET: str = "change-me-in-prod"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    # LLM（talk-002 实现，此处预留开关）
    LLM_PROVIDER: str = "mock"  # mock | claude | openai
    LLM_API_KEY: str | None = None
    AI_TALK_ENABLED: bool = False

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
