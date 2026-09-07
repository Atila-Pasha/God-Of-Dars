"""add timed shield activation and protection duration"""

import sqlalchemy as sa
from alembic import op

revision = "20260907_timed_shields"
down_revision = "402c3e44110d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shields",
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
    )
    op.create_check_constraint(
        "ck_shields_duration_minutes_positive",
        "shields",
        "duration_minutes >= 1",
    )
    op.add_column(
        "user_shields",
        sa.Column("active_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_shields", "active_until")
    op.drop_constraint(
        "ck_shields_duration_minutes_positive", "shields", type_="check"
    )
    op.drop_column("shields", "duration_minutes")
