"""add mine collection identity and daily quest completion metadata"""

import sqlalchemy as sa
from alembic import op

revision = "20260906_daily_quest_hardening"
down_revision = "20260906_daily_quests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("daily_quests", sa.Column("description", sa.String(1000), nullable=True))
    op.add_column("daily_quests", sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("daily_quest_progress", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("daily_quest_progress", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("daily_quest_progress", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("mines", sa.Column("collection_count", sa.BigInteger(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("mines", "collection_count")
    op.drop_column("daily_quest_progress", "completed_at")
    op.drop_column("daily_quest_progress", "updated_at")
    op.drop_column("daily_quest_progress", "created_at")
    op.drop_column("daily_quests", "metadata")
    op.drop_column("daily_quests", "description")
