"""Start monthly ranks from zero and allow training opponents."""

import sqlalchemy as sa
from alembic import op

revision = "20261023_monthly_rank"
down_revision = "20261022_ranked_seasons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_rank_npc",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Weekly profiles cannot be interpreted as the first monthly season.
    # Begin every existing player at 0 cups without changing today's limit.
    op.execute(
        """
        UPDATE rank_profiles
        SET season_start = date_trunc('month', now() AT TIME ZONE 'Asia/Tehran')
                           AT TIME ZONE 'Asia/Tehran',
            cups = 0,
            best_cups = 0,
            wins = 0,
            losses = 0
        """
    )


def downgrade() -> None:
    op.drop_column("users", "is_rank_npc")
