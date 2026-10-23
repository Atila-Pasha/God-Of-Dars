"""Retire training opponents while preserving historical attack references."""

import sqlalchemy as sa
from alembic import op

revision = "20261023_real_rank_opponents"
down_revision = "20261023_monthly_rank"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Old training rows may be referenced by resolved attacks. Keep those
    # records for history, but make them ineligible for all player flows.
    op.execute("UPDATE users SET is_active = false WHERE is_rank_npc = true")
    op.drop_column("users", "is_rank_npc")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_rank_npc", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE users SET is_rank_npc = true WHERE telegram_user_id < 0")
