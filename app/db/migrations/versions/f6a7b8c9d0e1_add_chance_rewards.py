"""add first-claimer chance boxes and captcha-protected chance cards"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    resource_enum = ENUM("COIN", "DIAMOND", "BANANA", name="resource_type", create_type=False)
    op.create_table(
        "chance_boxes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("resource_type", resource_enum, nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("claimed_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["claimed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chance_boxes_group_message", "chance_boxes", ["group_id", "telegram_message_id"], unique=True)
    op.create_table(
        "chance_cards",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("resource_type", resource_enum, nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("captcha_hash", sa.String(length=128), nullable=False),
        sa.Column("captcha_answer", sa.String(length=16), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_claimed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chance_cards_user_claimed", "chance_cards", ["user_id", "is_claimed"])


def downgrade() -> None:
    op.drop_index("ix_chance_cards_user_claimed", table_name="chance_cards")
    op.drop_table("chance_cards")
    op.drop_index("ix_chance_boxes_group_message", table_name="chance_boxes")
    op.drop_table("chance_boxes")
