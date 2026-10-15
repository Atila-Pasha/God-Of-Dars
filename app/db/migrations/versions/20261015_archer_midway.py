"""Record midway archer shots so each arrow is consumed once."""

import sqlalchemy as sa
from alembic import op

revision = "20261015_archer_midway"
down_revision = "20261015_archers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attacks", sa.Column("archer_processed_at", sa.DateTime(timezone=True))
    )
    op.create_index(
        "ix_attacks_archer_midway_due",
        "attacks",
        ["status", "created_at", "resolve_at"],
        postgresql_where=sa.text("archer_processed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_attacks_archer_midway_due", table_name="attacks")
    op.drop_column("attacks", "archer_processed_at")
