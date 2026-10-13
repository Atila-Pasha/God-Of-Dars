"""Track attacks that breach a destroyed castle and loot mine cargo."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261013_attack_mine_raid"
down_revision: str | Sequence[str] | None = "20261013_empty_target_bonus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("result_raid_damage", "mine_loot_coin", "mine_loot_diamond"):
        op.add_column(
            "attacks",
            sa.Column(column, sa.BigInteger(), server_default="0", nullable=False),
        )
        op.create_check_constraint(
            f"ck_attacks_{column.removeprefix('result_')}_non_negative",
            "attacks",
            f"{column} >= 0",
        )


def downgrade() -> None:
    for column in ("result_raid_damage", "mine_loot_coin", "mine_loot_diamond"):
        op.drop_constraint(
            f"ck_attacks_{column.removeprefix('result_')}_non_negative",
            "attacks",
            type_="check",
        )
        op.drop_column("attacks", column)
