"""应用配置：基于 pydantic-settings，从环境变量 / .env 读取。"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# 后端目录（.env 与 dev.db 都相对此目录解析）
# config.py 在 app/core/，需向上 3 层到 backend 根
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


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

    # LLM（talk-002 实现，OpenAI 兼容协议，不绑死供应商）
    LLM_PROVIDER: str = "mock"  # mock | openai_compatible
    LLM_API_KEY: str | None = None
    LLM_BASE_URL: str | None = None  # 如 https://tianqu.yzw.cn/v1
    LLM_MODEL: str | None = None  # 如 glm-5.2
    LLM_TIMEOUT: float = 30.0  # LLM 调用超时（秒，关闭 thinking 后约 2s，留余量）
    # extra_body（透传给 OpenAI SDK 的非标准参数，JSON 字符串）
    # glm-5.2 是 reasoning 模型，默认会先思考再输出（39s），关闭思考后 1.9s
    LLM_EXTRA_BODY: str = '{"thinking": {"type": "disabled"}}'
    AI_TALK_ENABLED: bool = False

    # 风险计算 Provider（risk-001 实现，mock → algorithm 可切换）
    RISK_PROVIDER: str = "mock"  # mock | algorithm

    # 每日跑批 cron（task-001 APScheduler，默认每日 00:00）
    BATCH_RUN_CRON: str = "0 0 * * *"

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
