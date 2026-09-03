"""add timed resource mines"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mines",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("level", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "last_collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "today", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False
        ),
        sa.Column("today_coin", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("today_diamond", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("today_banana", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("level >= 1", name="ck_mines_level_positive"),
        sa.CheckConstraint("today_coin >= 0", name="ck_mines_today_coin_non_negative"),
        sa.CheckConstraint(
            "today_diamond >= 0", name="ck_mines_today_diamond_non_negative"
        ),
        sa.CheckConstraint(
            "today_banana >= 0", name="ck_mines_today_banana_non_negative"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mines_user_id", "mines", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_mines_user_id", table_name="mines")
    op.drop_table("mines")
