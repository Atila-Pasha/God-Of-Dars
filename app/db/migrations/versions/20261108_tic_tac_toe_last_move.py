"""Remember the latest move for a stable advanced widget view."""

import sqlalchemy as sa
from alembic import op

revision = "20261108_ttt_last_move"
down_revision = "20261108_advanced_ttt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tic_tac_toe_games", sa.Column("last_move", sa.Integer()))


def downgrade() -> None:
    op.drop_column("tic_tac_toe_games", "last_move")
