"""store per-question rewards

Revision ID: a1b2c3d4e5f6
Revises: 9c4d7e1a2b30
Create Date: 2026-09-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "9c4d7e1a2b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column("coin_reward", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "questions",
        sa.Column(
            "diamond_reward", sa.BigInteger(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "questions",
        sa.Column(
            "banana_reward", sa.BigInteger(), server_default="0", nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_questions_coin_reward_non_negative",
        "questions",
        "coin_reward >= 0",
    )
    op.create_check_constraint(
        "ck_questions_diamond_reward_non_negative",
        "questions",
        "diamond_reward >= 0",
    )
    op.create_check_constraint(
        "ck_questions_banana_reward_non_negative",
        "questions",
        "banana_reward >= 0",
    )

    # One answer may grant multiple resource types. The resource type is part
    # of the idempotency key so coin and diamond rewards can coexist.
    op.drop_index("uq_library_reward_per_reference", table_name="rewards")
    op.create_index(
        "uq_library_reward_per_reference",
        "rewards",
        ["user_id", "source", "reference_type", "reference_id", "resource_type"],
        unique=True,
        postgresql_where=sa.text(
            "source IN ('DAILY_QUESTION', 'GROUP_QUESTION') "
            "AND reference_type IS NOT NULL AND reference_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "source IN ('DAILY_QUESTION', 'GROUP_QUESTION') "
            "AND reference_type IS NOT NULL AND reference_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_library_reward_per_reference", table_name="rewards")
    op.create_index(
        "uq_library_reward_per_reference",
        "rewards",
        ["user_id", "source", "reference_type", "reference_id"],
        unique=True,
        postgresql_where=sa.text(
            "source IN ('DAILY_QUESTION', 'GROUP_QUESTION') "
            "AND reference_type IS NOT NULL AND reference_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "source IN ('DAILY_QUESTION', 'GROUP_QUESTION') "
            "AND reference_type IS NOT NULL AND reference_id IS NOT NULL"
        ),
    )
    op.drop_constraint(
        "ck_questions_banana_reward_non_negative", "questions", type_="check"
    )
    op.drop_constraint(
        "ck_questions_diamond_reward_non_negative", "questions", type_="check"
    )
    op.drop_constraint(
        "ck_questions_coin_reward_non_negative", "questions", type_="check"
    )
    op.drop_column("questions", "banana_reward")
    op.drop_column("questions", "diamond_reward")
    op.drop_column("questions", "coin_reward")
