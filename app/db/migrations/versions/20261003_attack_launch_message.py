"""Persist attack launch messages until the battle result is delivered.

Revision ID: 20261003_attack_launch_message
Revises: 20261002_attack_banners
"""

import sqlalchemy as sa
from alembic import op

revision = "20261003_attack_launch_message"
down_revision = "20261002_attack_banners"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attacks", sa.Column("launch_chat_id", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "attacks", sa.Column("launch_message_id", sa.BigInteger(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("attacks", "launch_message_id")
    op.drop_column("attacks", "launch_chat_id")
