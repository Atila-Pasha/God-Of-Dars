"""Allow catalog shields to have a Telegram sticker."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_shield_sticker"
down_revision: str | Sequence[str] | None = "20261014_random_match_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shields", sa.Column("sticker", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("shields", "sticker")
