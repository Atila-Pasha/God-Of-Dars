"""Track coins awarded by the game for attacking an empty target."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261013_empty_target_bonus"
down_revision: str | Sequence[str] | None = "20261010_shield_emoji"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attacks",
        sa.Column(
            "bot_bonus_coin", sa.BigInteger(), server_default="0", nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_attacks_bot_bonus_coin_non_negative", "attacks", "bot_bonus_coin >= 0"
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_attacks_bot_bonus_coin_non_negative", "attacks", type_="check"
    )
    op.drop_column("attacks", "bot_bonus_coin")
