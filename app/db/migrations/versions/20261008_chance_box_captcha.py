"""Add letter captcha and one attempt per player to chance boxes.

Revision ID: 20261008_box_captcha
Revises: 20261008_box_message
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_box_captcha"
down_revision: str | Sequence[str] | None = "20261008_box_message"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chance_boxes", sa.Column("captcha_answer", sa.String(8)))
    op.create_table(
        "chance_box_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "box_id",
            sa.BigInteger(),
            sa.ForeignKey("chance_boxes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("box_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("chance_box_attempts")
    op.drop_column("chance_boxes", "captcha_answer")
