"""Alembic 环境配置。

关键点：
1. 从 app.core.config.settings 注入 DATABASE_URL（alembic.ini 的 url 留空）
2. target_metadata = Base.metadata（来自 app.core.database）
3. import app.models —— 否则 autogenerate 检测不到表，生成空迁移！
4. render_as_batch=True —— SQLite 下支持后续 alter column（PG 自动忽略）
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.database import Base

# 关键：导入所有模型，使 Base.metadata 包含全部表定义
import app.models  # noqa: F401

config = context.config

# 注入 DATABASE_URL（覆盖 alembic.ini 留空的 url）
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直连数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
