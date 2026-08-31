"""add referral reward idempotency constraint

Revision ID: 8f2a6c1d4b70
Revises: 7e1d2c4f6a90
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8f2a6c1d4b70"
down_revision: str | Sequence[str] | None = "7e1d2c4f6a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_referral_reward_per_reference",
        "rewards",
        ["user_id", "source", "reference_type", "reference_id"],
        unique=True,
        postgresql_where=sa.text(
            "source = 'REFERRAL' AND reference_type IS NOT NULL "
            "AND reference_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "source = 'REFERRAL' AND reference_type IS NOT NULL "
            "AND reference_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_referral_reward_per_reference",
        table_name="rewards",
        postgresql_where=sa.text(
            "source = 'REFERRAL' AND reference_type IS NOT NULL "
            "AND reference_id IS NOT NULL"
        ),
    )
