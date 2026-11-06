"""Add persistent matches with escrow and move deadline."""

import sqlalchemy as sa
from alembic import op

revision = "20261106_tic_tac_toe"
down_revision = "20261023_broadcast_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tic_tac_toe_games",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "challenger_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("opponent_id", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("stake_type", sa.String(16)),
        sa.Column("stake_amount", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="invited"),
        sa.Column("board", sa.String(9), nullable=False, server_default="........."),
        sa.Column("turn_id", sa.BigInteger()),
        sa.Column("winner_id", sa.BigInteger()),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("escrowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("challenger_message_id", sa.BigInteger()),
        sa.Column("opponent_message_id", sa.BigInteger()),
        sa.Column(
            "challenger_widget", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "opponent_widget", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("stake_amount >= 0", name="ck_ttt_stake_nonnegative"),
        sa.CheckConstraint("length(board) = 9", name="ck_ttt_board_length"),
    )
    op.create_index(
        "ix_ttt_status_deadline", "tic_tac_toe_games", ["status", "deadline_at"]
    )
    op.create_index(
        "ix_ttt_challenger_status", "tic_tac_toe_games", ["challenger_id", "status"]
    )
    op.create_index(
        "ix_ttt_opponent_status", "tic_tac_toe_games", ["opponent_id", "status"]
    )


def downgrade() -> None:
    op.drop_table("tic_tac_toe_games")
