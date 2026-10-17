"""Keep the knight's protection for an attack after its midway hit."""

import sqlalchemy as sa
from alembic import op

revision = "20261017_knight_snapshot"
down_revision = "20261017_knights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attacks",
        sa.Column(
            "guard_reduction_snapshot", sa.Integer(), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("attacks", "guard_reduction_snapshot")
