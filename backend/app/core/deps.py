"""FastAPI 依赖：数据库会话等。"""

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.core.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """请求级数据库会话，自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
