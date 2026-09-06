"""add public teacher descriptions"""

import sqlalchemy as sa
from alembic import op

revision = "3c4d5e6f7a8b"
down_revision = "2b3c4d5e6f7a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("teachers", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("teachers", "description")
