"""add tasks unique constraint (idempotency)

Revision ID: c4a2b9d1e0f1
Revises: 0baedee4c6c7
Create Date: 2026-09-09 00:00:00.000000

task-001：催收任务幂等三元组 batch_id + order_id + day_offset 唯一约束。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4a2b9d1e0f1"
down_revision: Union[str, None] = "0baedee4c6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT = "uq_tasks_batch_order_day"


def upgrade() -> None:
    # SQLite 不支持 ALTER TABLE ADD CONSTRAINT，
    # alembic batch mode 会自动重建表并保留数据；
    # tasks 表在 task-001 之前从不写入（无历史数据），重建安全。
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            _CONSTRAINT, ["batch_id", "order_id", "day_offset"]
        )


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_constraint(_CONSTRAINT, type_="unique")
