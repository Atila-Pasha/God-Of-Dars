"""Allow marking a chance-box Telegram message as deleted.

Revision ID: 20261008_box_message
Revises: 20261006_slogan_reward
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261008_box_message"
down_revision: str | Sequence[str] | None = "20261006_slogan_reward"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("chance_boxes", "telegram_message_id", nullable=True)


def downgrade() -> None:
    op.execute(
        "UPDATE chance_boxes SET telegram_message_id = -id "
        "WHERE telegram_message_id IS NULL"
    )
    op.alter_column("chance_boxes", "telegram_message_id", nullable=False)
