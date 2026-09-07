"""remove win battle quests and enforce the current daily quest types"""

from collections.abc import Sequence

from alembic import op

revision = "20260907_daily_cleanup"
down_revision: str | Sequence[str] | None = "20260907_teacher_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_daily_quests_type", "daily_quests", type_="check")
    op.create_check_constraint(
        "ck_daily_quests_type",
        "daily_quests",
        "quest_type IN ('DAILY_LOGIN','ANSWER_DAILY_QUESTION','CORRECT_ANSWERS','COMPLETE_BATTLES','COLLECT_MINE','JOIN_CHANNEL')",
    )
    op.execute("DELETE FROM daily_quests WHERE quest_type = 'WIN_BATTLES'")


def downgrade() -> None:
    op.drop_constraint("ck_daily_quests_type", "daily_quests", type_="check")
    op.create_check_constraint(
        "ck_daily_quests_type",
        "daily_quests",
        "quest_type IN ('DAILY_LOGIN','ANSWER_DAILY_QUESTION','CORRECT_ANSWERS','COMPLETE_BATTLES','COLLECT_MINE','JOIN_CHANNEL','WIN_BATTLES')",
    )
