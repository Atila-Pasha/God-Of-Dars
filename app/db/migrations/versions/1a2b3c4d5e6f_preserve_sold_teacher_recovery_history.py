"""keep hospital history when an owned teacher is sold"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1b2c3d4e5f6a"
down_revision: str | Sequence[str] | None = "0f1e2d3c4b5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "recoveries_user_teacher_id_fkey", "recoveries", type_="foreignkey"
    )
    op.alter_column(
        "recoveries",
        "user_teacher_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.create_foreign_key(
        "recoveries_user_teacher_id_fkey",
        "recoveries",
        "user_teachers",
        ["user_teacher_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "recoveries_user_teacher_id_fkey", "recoveries", type_="foreignkey"
    )
    op.alter_column(
        "recoveries",
        "user_teacher_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.create_foreign_key(
        "recoveries_user_teacher_id_fkey",
        "recoveries",
        "user_teachers",
        ["user_teacher_id"],
        ["id"],
        ondelete="CASCADE",
    )
