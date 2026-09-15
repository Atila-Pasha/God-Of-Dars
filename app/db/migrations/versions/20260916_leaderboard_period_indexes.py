"""add indexes for period leaderboards

Revision ID: 20260916_leaderboard_indexes
Revises: 20260914_starter_teacher
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260916_leaderboard_indexes"
down_revision: str | Sequence[str] | None = "20260914_starter_teacher"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_answers_answered_user",
        "answers",
        ["answered_at", "user_id"],
    )
    op.create_index(
        "ix_attacks_leaderboard_resolved",
        "attacks",
        ["resolved_at", "attacker_id"],
        postgresql_where="status = 'RESOLVED' AND is_successful = true",
    )
    op.create_index(
        "ix_transactions_leaderboard_xp",
        "transactions",
        ["created_at", "user_id"],
        postgresql_where="resource_type = 'BANANA' AND amount > 0",
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_leaderboard_xp", table_name="transactions")
    op.drop_index("ix_attacks_leaderboard_resolved", table_name="attacks")
    op.drop_index("ix_answers_answered_user", table_name="answers")
