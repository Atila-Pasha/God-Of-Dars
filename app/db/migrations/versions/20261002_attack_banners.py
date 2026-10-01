"""Persist group attack origin and teacher details for battle reports.

Revision ID: 20261002_attack_banners
Revises: 20260923_economy_catalog
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261002_attack_banners"
down_revision: str | Sequence[str] | None = "20260923_economy_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attacks", sa.Column("source_chat_id", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "attacks", sa.Column("teacher_name_snapshot", sa.String(100), nullable=True)
    )
    op.add_column(
        "attacks", sa.Column("teacher_emoji_snapshot", sa.String(32), nullable=True)
    )
    op.add_column(
        "attacks", sa.Column("teacher_ability_snapshot", sa.Text(), nullable=True)
    )
    op.add_column(
        "attacks",
        sa.Column(
            "result_teacher_injury",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("attacks", "result_teacher_injury")
    op.drop_column("attacks", "teacher_ability_snapshot")
    op.drop_column("attacks", "teacher_emoji_snapshot")
    op.drop_column("attacks", "teacher_name_snapshot")
    op.drop_column("attacks", "source_chat_id")
