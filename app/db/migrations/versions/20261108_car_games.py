"""Store server-authoritative car runs and their paid rewards."""

import sqlalchemy as sa
from alembic import op

revision = "20261108_car_games"
down_revision = "20261108_ttt_10x10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "car_games",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("lane", sa.Integer(), nullable=False),
        sa.Column("tick", sa.Integer(), nullable=False),
        sa.Column("coin", sa.Integer(), nullable=False),
        sa.Column("diamond", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.BigInteger()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("next_tick_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("lane BETWEEN 0 AND 2", name="ck_car_game_lane"),
        sa.CheckConstraint(
            "tick >= 0 AND coin >= 0 AND diamond >= 0", name="ck_car_game_counts"
        ),
    )
    op.create_index("ix_car_games_user_status", "car_games", ["user_id", "status"])
    op.create_index("ix_car_games_due", "car_games", ["status", "next_tick_at"])


def downgrade() -> None:
    op.drop_index("ix_car_games_due", table_name="car_games")
    op.drop_index("ix_car_games_user_status", table_name="car_games")
    op.drop_table("car_games")
