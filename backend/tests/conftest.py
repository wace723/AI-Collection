"""pytest 公共夹具。

测试用临时 SQLite（内存）+ create_all，不走 Alembic 迁移。
迁移正确性由 init.sh 里 `alembic upgrade head` 单独验证，两条路径分开。
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import get_db
from app.core.database import Base
from app.main import app


@pytest.fixture()
def db_engine():
    """每测试函数一个内存 SQLite，干净隔离。

    用 StaticPool 共享单一连接，否则内存 SQLite 的表只对建表连接可见，
    TestClient 在其他线程/连接查询时会报 no such table。
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    """TestClient，覆盖 get_db 指向临时 session。"""

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def seed_users(db_session):
    """插入各角色测试用户，返回 username→password 映射。"""
    from app.core.security import hash_password
    from app.models.user import User

    users = [
        ("admin", "管理员", "ADMIN"),
        ("supervisor", "催收主管", "SUPERVISOR"),
        ("collector1", "催收员1", "COLLECTOR"),
    ]
    password = "admin123"
    for username, display_name, role in users:
        db_session.add(
            User(
                username=username,
                password_hash=hash_password(password),
                display_name=display_name,
                role=role,
                is_active=True,
            )
        )
    db_session.commit()
    return {u[0]: password for u in users}
