"""Remember recent random opponents to avoid immediate repeats."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_random_match_history"
down_revision: str | Sequence[str] | None = "20261013_revenge_free_shield"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "random_attack_selections",
        sa.Column(
            "recent_target_ids",
            sa.String(length=256),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("random_attack_selections", "recent_target_ids")
