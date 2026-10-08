"""Make each shield's daily purchase limit editable by admins."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_shield_daily_limit"
down_revision: str | Sequence[str] | None = "20261008_shield_descriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shields", sa.Column("daily_limit", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_shields_daily_limit_positive",
        "shields",
        "daily_limit IS NULL OR daily_limit >= 1",
    )
    op.execute("UPDATE shields SET daily_limit = 2 WHERE name = 'سپر زنگ تفریح'")
    op.execute("UPDATE shields SET daily_limit = 1 WHERE name = 'سپر آلودگی هوا'")


def downgrade() -> None:
    op.drop_constraint("ck_shields_daily_limit_positive", "shields", type_="check")
    op.drop_column("shields", "daily_limit")
