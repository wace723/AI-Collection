"""数据库引擎、会话工厂、声明式基类与时间戳混入。"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, create_engine, func, inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.core.config import settings


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


# SQLite 需要 check_same_thread=False（FastAPI 多线程用）；PG 无害省略
connect_args = {"check_same_thread": False} if _is_sqlite(settings.DATABASE_URL) else {}

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类。"""

    # 跨库 JSON：SQLite 用 JSON，PostgreSQL 用 JSONB
    type_annotation_map = {dict[str, Any]: JSON().with_variant(JSONB, "postgresql")}


class TimestampMixin:
    """提供 created_at / updated_at 的混入。"""

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )


class CreatedAtMixin:
    """仅 created_at（用于只增不改的记录，如 task_results/ai_conversations）。"""

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, server_default=func.now()
    )


def is_sqlite() -> bool:
    """运行时判断当前是否 SQLite（迁移/测试用）。"""
    return _is_sqlite(settings.DATABASE_URL)
