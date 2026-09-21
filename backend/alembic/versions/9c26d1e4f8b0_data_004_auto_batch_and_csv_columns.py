"""data-004 auto batch and csv columns

Revision ID: 9c26d1e4f8b0
Revises: 8b15c0d3e7a9
Create Date: 2026-09-21 10:00:00.000000

Order 新增 engineering_bureau（工程局单位）、subsidiary（下属单位）字段，
适配待支付/已支付 CSV 新增的两列（40 列）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c26d1e4f8b0'
down_revision: Union[str, None] = '8b15c0d3e7a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('engineering_bureau', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('subsidiary', sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('subsidiary')
        batch_op.drop_column('engineering_bureau')
