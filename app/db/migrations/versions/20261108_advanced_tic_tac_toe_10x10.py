"""Allow ten by ten games while preserving existing fifteen by fifteen games."""

from alembic import op

revision = "20261108_ttt_10x10"
down_revision = "20261108_ttt_last_move"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_ttt_board_length", "tic_tac_toe_games", type_="check")
    op.create_check_constraint(
        "ck_ttt_board_length",
        "tic_tac_toe_games",
        "(variant = 'classic' AND length(board) = 9) OR "
        "(variant = 'advanced' AND length(board) IN (100, 225))",
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM tic_tac_toe_games WHERE variant = 'advanced' AND length(board) = 100"
    )
    op.drop_constraint("ck_ttt_board_length", "tic_tac_toe_games", type_="check")
    op.create_check_constraint(
        "ck_ttt_board_length",
        "tic_tac_toe_games",
        "(variant = 'classic' AND length(board) = 9) OR "
        "(variant = 'advanced' AND length(board) = 225)",
    )
