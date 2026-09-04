"""add expiry timestamps to chance boxes"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chance_boxes", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE chance_boxes SET expires_at = created_at + interval '2 minutes' WHERE expires_at IS NULL")
    op.alter_column("chance_boxes", "expires_at", nullable=False)
    op.create_index("ix_chance_boxes_expires_at", "chance_boxes", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_chance_boxes_expires_at", table_name="chance_boxes")
    op.drop_column("chance_boxes", "expires_at")
