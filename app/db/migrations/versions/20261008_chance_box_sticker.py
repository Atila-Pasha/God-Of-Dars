"""Track chance box stickers until the box is completed or expires.

Revision ID: 20261008_box_sticker
Revises: 20261008_box_captcha
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_box_sticker"
down_revision: str | Sequence[str] | None = "20261008_box_captcha"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chance_boxes", sa.Column("sticker_message_id", sa.BigInteger()))


def downgrade() -> None:
    op.drop_column("chance_boxes", "sticker_message_id")
