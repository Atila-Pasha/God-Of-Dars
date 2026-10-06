"""Remember when each commander last claimed the slogan reward."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_slogan_reward"
down_revision: str | Sequence[str] | None = "20261006_hospital_levels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("last_slogan_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "last_slogan_at")
