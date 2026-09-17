"""data-003 collection state machine

Revision ID: 8b15c0d3e7a9
Revises: 7a068ab18bfc
Create Date: 2026-09-17 10:00:00.000000

Order 新增 collection_state 字段 + 数据回填：
- 现有 Order 按 win_bid_date + 首轮 day_offset 回填 collection_state
  （已过首轮且待支付→PENDING_COLLECTION，未到→NO_NEED，已支付→FINALIZED）
- 现有 Task.result 旧值映射：PAID/DISPUTE/LOST_CONTACT/OTHER→REACHED，PROMISE→UNREACHED
- 现有 Task.status=PENDING（PROMISE 改期态）→ IN_PROGRESS（去掉 PENDING 改期态）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b15c0d3e7a9'
down_revision: Union[str, None] = '7a068ab18bfc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Order 加 collection_state 字段（默认 NO_NEED，非空，索引）
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'collection_state',
                sa.String(length=24),
                nullable=False,
                server_default='NO_NEED',
            )
        )
        batch_op.create_index('ix_orders_collection_state', ['collection_state'])

    bind = op.get_bind()

    # 2. 回填 Order.collection_state：
    #    已支付 → FINALIZED
    #    待支付 + 已过首轮时点 → PENDING_COLLECTION
    #    待支付 + 未到首轮时点（或无配置/无 risk_tier）→ NO_NEED
    #
    # 首轮 day_offset = 该 risk_tier 在 collection_schedules 中 day_offset 最小值（is_active=1）
    # 用子查询取首轮 day_offset，join orders 自算。
    bind.execute(
        sa.text(
            """
            UPDATE orders
            SET collection_state = CASE
                WHEN pay_status = 'PAID' THEN 'FINALIZED'
                WHEN win_bid_date IS NOT NULL
                     AND risk_tier IS NOT NULL
                     AND (
                         SELECT MIN(cs.day_offset)
                         FROM collection_schedules cs
                         WHERE cs.risk_tier = orders.risk_tier
                           AND cs.is_active = 1
                     ) IS NOT NULL
                     AND date(win_bid_date, '+' || (
                         SELECT MIN(cs.day_offset)
                         FROM collection_schedules cs
                         WHERE cs.risk_tier = orders.risk_tier
                           AND cs.is_active = 1
                     ) || ' days') <= date('now')
                THEN 'PENDING_COLLECTION'
                ELSE 'NO_NEED'
            END
            """
        )
    )

    # 3. 回填 Task.result 旧值 → 新两分类
    #    PAID/DISPUTE/LOST_CONTACT/OTHER → REACHED（历史已处理视为已接通）
    #    PROMISE → UNREACHED（未接通的改期）
    bind.execute(
        sa.text(
            """
            UPDATE tasks
            SET result = CASE result
                WHEN 'PAID' THEN 'REACHED'
                WHEN 'DISPUTE' THEN 'REACHED'
                WHEN 'LOST_CONTACT' THEN 'REACHED'
                WHEN 'OTHER' THEN 'REACHED'
                WHEN 'PROMISE' THEN 'UNREACHED'
                ELSE result
            END
            WHERE result IS NOT NULL
               AND result IN ('PAID', 'DISPUTE', 'LOST_CONTACT', 'OTHER', 'PROMISE')
            """
        )
    )

    # 4. 回填 Task.status：PENDING（PROMISE 改期态）→ IN_PROGRESS
    #    去掉 PENDING 改期态，统一回 IN_PROGRESS（保留 assignee）
    bind.execute(
        sa.text(
            """
            UPDATE tasks
            SET status = 'IN_PROGRESS'
            WHERE status = 'PENDING'
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_index('ix_orders_collection_state')
        batch_op.drop_column('collection_state')
    # 注意：Task.result 旧值映射与 PENDING→IN_PROGRESS 不可逆，
    # downgrade 仅回滚 schema，历史回填值不恢复（符合 design.md Migration Plan）。
