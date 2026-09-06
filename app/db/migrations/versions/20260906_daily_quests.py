"""add database-driven daily quests"""

import sqlalchemy as sa
from alembic import op

revision = "20260906_daily_quests"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_quests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("quest_type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("target", sa.Integer(), nullable=False),
        sa.Column("rewards", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("target > 0", name="ck_daily_quests_target_positive"),
        sa.CheckConstraint("quest_type IN ('DAILY_LOGIN','ANSWER_DAILY_QUESTION','CORRECT_ANSWERS','COMPLETE_BATTLES','WIN_BATTLES','COLLECT_MINE','JOIN_CHANNEL')", name="ck_daily_quests_type"),
    )
    op.create_index("ix_daily_quests_date_active", "daily_quests", ["activity_date", "is_active"])
    op.create_table(
        "daily_quest_progress",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quest_id", sa.BigInteger(), sa.ForeignKey("daily_quests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "quest_id", name="uq_daily_quest_progress_user_quest"),
        sa.CheckConstraint("progress >= 0", name="ck_daily_quest_progress_non_negative"),
    )
    op.create_index("ix_daily_quest_progress_user_date", "daily_quest_progress", ["user_id", "activity_date"])
    op.create_table(
        "daily_quest_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "activity_date", "event_key", name="uq_daily_quest_event_idempotency"),
    )


def downgrade() -> None:
    op.drop_table("daily_quest_events")
    op.drop_index("ix_daily_quest_progress_user_date", table_name="daily_quest_progress")
    op.drop_table("daily_quest_progress")
    op.drop_index("ix_daily_quests_date_active", table_name="daily_quests")
    op.drop_table("daily_quests")
