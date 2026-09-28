"""talk-003 admin talk config: template_type/system_prompt/user_prompt + scene ROUND_N migration

Revision ID: a1b2c3d4e5f6
Revises: 9c26d1e4f8b0
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "9c26d1e4f8b0"
branch_labels = None
depends_on = None


# 旧 scene 值 → 新 ROUND_N 映射
_SCENE_MAP = {
    "FIRST": "ROUND_1",
    "SECOND": "ROUND_2",
    "THIRD": "ROUND_3",
}


def upgrade() -> None:
    # 1. talk_templates 加列：template_type / system_prompt / user_prompt
    with op.batch_alter_table("talk_templates", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "template_type",
                sa.String(length=16),
                nullable=False,
                server_default="FIXED",
            )
        )
        batch_op.add_column(sa.Column("system_prompt", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("user_prompt", sa.Text(), nullable=True))
    # 给 template_type 建索引（加列后单独建，兼容 SQLite batch 重建）
    with op.batch_alter_table("talk_templates", schema=None) as batch_op:
        batch_op.create_index(
            "ix_talk_templates_template_type", ["template_type"], unique=False
        )

    # 2. collection_schedules scene 值映射 FIRST/SECOND/THIRD → ROUND_N
    bind = op.get_bind()
    for old, new in _SCENE_MAP.items():
        bind.execute(
            sa.text(
                "UPDATE collection_schedules SET scene = :new WHERE scene = :old"
            ).bindparams(new=new, old=old)
        )

    # 3. tasks scene 值同步映射
    for old, new in _SCENE_MAP.items():
        bind.execute(
            sa.text(
                "UPDATE tasks SET scene = :new WHERE scene = :old"
            ).bindparams(new=new, old=old)
        )

    # 4. 清空现有 6 条默认话术模板（D5 决策：丢掉重新配）
    bind.execute(sa.text("DELETE FROM talk_templates"))


def downgrade() -> None:
    # 回滚：还原 scene 值 + 删除新列
    bind = op.get_bind()
    for old, new in _SCENE_MAP.items():
        bind.execute(
            sa.text(
                "UPDATE collection_schedules SET scene = :old WHERE scene = :new"
            ).bindparams(old=old, new=new)
        )
        bind.execute(
            sa.text(
                "UPDATE tasks SET scene = :old WHERE scene = :new"
            ).bindparams(old=old, new=new)
        )

    with op.batch_alter_table("talk_templates", schema=None) as batch_op:
        batch_op.drop_index("ix_talk_templates_template_type")
        batch_op.drop_column("user_prompt")
        batch_op.drop_column("system_prompt")
        batch_op.drop_column("template_type")
