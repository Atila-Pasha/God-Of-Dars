"""Track received attacks and the free one-hour protection."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261013_revenge_free_shield"
down_revision: str | Sequence[str] | None = "20261013_repair_recoveries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "attacks_since_free_shield",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column("users", sa.Column("free_shield_until", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_users_free_shield_attack_count",
        "users",
        "attacks_since_free_shield BETWEEN 0 AND 4",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_free_shield_attack_count", "users", type_="check")
    op.drop_column("users", "free_shield_until")
    op.drop_column("users", "attacks_since_free_shield")
