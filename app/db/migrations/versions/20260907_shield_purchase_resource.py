"""add configurable shield purchase resource"""

import sqlalchemy as sa
from alembic import op

revision = "20260907_shield_currency"
down_revision = "20260907_timed_shields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shields",
        sa.Column(
            "purchase_resource",
            sa.Enum("COIN", "DIAMOND", "BANANA", name="resource_type"),
            nullable=False,
            server_default="COIN",
        ),
    )


def downgrade() -> None:
    op.drop_column("shields", "purchase_resource")
