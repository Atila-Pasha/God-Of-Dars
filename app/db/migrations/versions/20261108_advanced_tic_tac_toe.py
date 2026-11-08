"""Add fifteen by fifteen five-in-a-row matches."""

import sqlalchemy as sa
from alembic import op

revision = "20261108_advanced_ttt"
down_revision = "20261106_tic_tac_toe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tic_tac_toe_games",
        sa.Column("variant", sa.String(16), nullable=False, server_default="classic"),
    )
    op.alter_column(
        "tic_tac_toe_games",
        "board",
        type_=sa.String(225),
        existing_type=sa.String(9),
        existing_nullable=False,
    )
    op.drop_constraint("ck_ttt_board_length", "tic_tac_toe_games", type_="check")
    op.create_check_constraint(
        "ck_ttt_board_length",
        "tic_tac_toe_games",
        "(variant = 'classic' AND length(board) = 9) OR (variant = 'advanced' AND length(board) = 225)",
    )


def downgrade() -> None:
    op.execute("DELETE FROM tic_tac_toe_games WHERE variant = 'advanced'")
    op.drop_constraint("ck_ttt_board_length", "tic_tac_toe_games", type_="check")
    op.create_check_constraint(
        "ck_ttt_board_length", "tic_tac_toe_games", "length(board) = 9"
    )
    op.alter_column(
        "tic_tac_toe_games",
        "board",
        type_=sa.String(9),
        existing_type=sa.String(225),
        existing_nullable=False,
    )
    op.drop_column("tic_tac_toe_games", "variant")
