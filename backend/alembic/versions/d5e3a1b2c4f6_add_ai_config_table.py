"""add ai_config table (talk-002)

Revision ID: d5e3a1b2c4f6
Revises: c4a2b9d1e0f1
Create Date: 2026-09-09 00:00:00.000000

talk-002：AI 话术运行时配置单行表（主管前端可配 api_key/base_url/model）。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d5e3a1b2c4f6"
down_revision: Union[str, None] = "c4a2b9d1e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("api_key", sa.String(length=255), nullable=True),
        sa.Column("base_url", sa.String(length=255), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
    )


def downgrade() -> None:
    op.drop_table("ai_config")
