"""add configurable teacher purchase resource"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260907_teacher_currency"
down_revision: str | Sequence[str] | None = "20260907_study_packs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "teachers",
        sa.Column(
            "purchase_resource",
            sa.Enum("COIN", "DIAMOND", "BANANA", name="resource_type"),
            nullable=False,
            server_default="COIN",
        ),
    )


def downgrade() -> None:
    op.drop_column("teachers", "purchase_resource")
