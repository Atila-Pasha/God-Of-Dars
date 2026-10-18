"""Persist five-hour recovery and health for both castle guards."""

import sqlalchemy as sa
from alembic import op

revision = "20261018_guard_recovery"
down_revision = "20261017_knight_death"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_archers",
        sa.Column("current_hp", sa.Integer(), nullable=False, server_default="100"),
    )
    op.add_column(
        "user_archers", sa.Column("recovery_until", sa.DateTime(timezone=True))
    )
    op.add_column(
        "user_knights", sa.Column("recovery_until", sa.DateTime(timezone=True))
    )
    op.execute(
        sa.text(
            "UPDATE user_knights SET recovery_until = NOW() + INTERVAL '5 hours' "
            "WHERE current_hp = 0"
        )
    )
    op.execute(
        sa.text(
            """UPDATE user_archers AS owned
               SET current_hp = GREATEST(100, catalog.power * 5)
                   + (owned.level - 1) * GREATEST(
                       1, CEIL(GREATEST(100, catalog.power * 5) * 0.08)::integer
                   )
               FROM archers AS catalog
               WHERE catalog.id = owned.archer_id"""
        )
    )
    op.drop_constraint("ck_user_archers_level", "user_archers", type_="check")
    op.create_check_constraint(
        "ck_user_archers_level",
        "user_archers",
        "level >= 1 AND current_hp >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_user_archers_level", "user_archers", type_="check")
    op.create_check_constraint("ck_user_archers_level", "user_archers", "level >= 1")
    op.drop_column("user_knights", "recovery_until")
    op.drop_column("user_archers", "recovery_until")
    op.drop_column("user_archers", "current_hp")
