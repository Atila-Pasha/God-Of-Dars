"""group attack records and make attack XP idempotent"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2c3d4e5f6a7b"
down_revision: str | Sequence[str] | None = "1b2c3d4e5f6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "attacks",
        sa.Column("attack_command_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "attacks",
        sa.Column(
            "attack_xp_awarded",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_attacks_attack_command_id",
        "attacks",
        ["attack_command_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_attacks_attack_command_id", table_name="attacks")
    op.drop_column("attacks", "attack_xp_awarded")
    op.drop_column("attacks", "attack_command_id")
