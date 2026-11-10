"""Add persistent chess matches and wager escrow metadata."""

import sqlalchemy as sa
from alembic import op

revision = "20261110_chess_games"
down_revision = "20261108_car_games"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chess_games",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "challenger_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("opponent_id", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("stake_type", sa.String(16)),
        sa.Column("stake_amount", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("moves", sa.Text(), nullable=False),
        sa.Column("turn_id", sa.BigInteger()),
        sa.Column("winner_id", sa.BigInteger()),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("escrowed", sa.Boolean(), nullable=False),
        sa.Column("challenger_message_id", sa.BigInteger()),
        sa.Column("opponent_message_id", sa.BigInteger()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("stake_amount >= 0", name="ck_chess_stake_nonnegative"),
    )
    op.create_index(
        "ix_chess_status_deadline", "chess_games", ["status", "deadline_at"]
    )
    op.create_index(
        "ix_chess_challenger_status", "chess_games", ["challenger_id", "status"]
    )
    op.create_index(
        "ix_chess_opponent_status", "chess_games", ["opponent_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_chess_opponent_status", table_name="chess_games")
    op.drop_index("ix_chess_challenger_status", table_name="chess_games")
    op.drop_index("ix_chess_status_deadline", table_name="chess_games")
    op.drop_table("chess_games")
