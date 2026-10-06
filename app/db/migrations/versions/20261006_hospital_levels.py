"""Add a persistent hospital level to each commander."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_hospital_levels"
down_revision: str | Sequence[str] | None = "20261005_mine_daily_limit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("hospital_level", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_check_constraint(
        "ck_users_hospital_level_positive", "users", "hospital_level >= 1"
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_hospital_level_positive", "users", type_="check")
    op.drop_column("users", "hospital_level")
