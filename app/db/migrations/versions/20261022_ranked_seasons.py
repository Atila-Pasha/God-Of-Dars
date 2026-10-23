"""Add weekly ranked seasons and command settlement markers."""

import sqlalchemy as sa
from alembic import op

revision = "20261022_ranked_seasons"
down_revision = "20261018_guard_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rank_profiles",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("season_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cups", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("best_cups", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_date", sa.Date()),
        sa.Column("daily_attacks", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("cups >= 0", name="ck_rank_profiles_cups"),
        sa.CheckConstraint("daily_attacks BETWEEN 0 AND 20", name="ck_rank_profiles_daily_attacks"),
    )
    op.create_index("ix_rank_profiles_season_cups", "rank_profiles", ["season_start", "cups"])
    op.add_column("attacks", sa.Column("is_ranked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("attacks", sa.Column("rank_settled", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("attacks", "rank_settled")
    op.drop_column("attacks", "is_ranked")
    op.drop_index("ix_rank_profiles_season_cups", table_name="rank_profiles")
    op.drop_table("rank_profiles")
