"""keep attack history when an owned teacher is sold"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0f1e2d3c4b5a"
down_revision: str | Sequence[str] | None = "2b3c4d5e6f7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("attacks_teacher_id_fkey", "attacks", type_="foreignkey")
    op.alter_column(
        "attacks",
        "teacher_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.create_foreign_key(
        "attacks_teacher_id_fkey",
        "attacks",
        "user_teachers",
        ["teacher_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # A downgrade is only safe before any sold-teacher history exists.
    op.drop_constraint("attacks_teacher_id_fkey", "attacks", type_="foreignkey")
    op.alter_column(
        "attacks",
        "teacher_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.create_foreign_key(
        "attacks_teacher_id_fkey",
        "attacks",
        "user_teachers",
        ["teacher_id"],
        ["id"],
        ondelete="RESTRICT",
    )
