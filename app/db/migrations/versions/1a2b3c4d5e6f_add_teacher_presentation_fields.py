"""add optional teacher presentation fields"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1a2b3c4d5e6f"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("teachers", sa.Column("sticker", sa.String(length=255), nullable=True))
    op.add_column("teachers", sa.Column("emoji", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("teachers", "emoji")
    op.drop_column("teachers", "sticker")
