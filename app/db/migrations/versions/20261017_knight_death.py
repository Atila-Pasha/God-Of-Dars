"""Record permanent knight death in attack reports."""

import sqlalchemy as sa
from alembic import op

revision = "20261017_knight_death"
down_revision = "20261017_knight_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attacks",
        sa.Column(
            "guard_died_snapshot",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(sa.text("DELETE FROM user_knights WHERE current_hp = 0"))


def downgrade() -> None:
    op.drop_column("attacks", "guard_died_snapshot")
