"""store Telegram message ids for group question replies

Revision ID: 9c4d7e1a2b30
Revises: 8f2a6c1d4b70
Create Date: 2026-09-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c4d7e1a2b30"
down_revision: str | Sequence[str] | None = "8f2a6c1d4b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "group_questions",
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("group_questions", "telegram_message_id")
