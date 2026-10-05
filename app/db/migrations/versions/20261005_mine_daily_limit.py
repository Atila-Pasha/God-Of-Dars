"""Track daily mine production independently of uncollected cargo."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_mine_daily_limit"
down_revision: str | Sequence[str] | None = "20261005_shield_arsenal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mines",
        sa.Column(
            "daily_produced_minutes", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_mines_daily_produced_non_negative", "mines", "daily_produced_minutes >= 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_mines_daily_produced_non_negative", "mines", type_="check")
    op.drop_column("mines", "daily_produced_minutes")
