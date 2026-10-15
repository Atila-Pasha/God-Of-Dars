"""Close recovery records interrupted by a later attack."""

from collections.abc import Sequence

from alembic import op

revision: str = "20261013_repair_recoveries"
down_revision: str | Sequence[str] | None = "20261013_attack_mine_raid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older versions allowed an in-flight attack to injure an admitted teacher.
    # Their recovery row stayed open and blocked the unique active-recovery
    # index, so starting treatment again failed even with a free bed.
    op.execute(
        """
        UPDATE recoveries AS recovery
        SET completed_at = CURRENT_TIMESTAMP
        FROM user_teachers AS owned
        WHERE recovery.user_teacher_id = owned.id
          AND recovery.completed_at IS NULL
          AND owned.status <> 'RECOVERING'
        """
    )


def downgrade() -> None:
    # Reopening interrupted treatments would recreate the invalid state.
    pass
