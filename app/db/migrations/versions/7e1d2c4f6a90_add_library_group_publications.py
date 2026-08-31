"""add group question publications and answer idempotency constraints

Revision ID: 7e1d2c4f6a90
Revises: 3bd7baf040a8
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7e1d2c4f6a90"
down_revision: str | Sequence[str] | None = "3bd7baf040a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "group_questions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("question_id", sa.BigInteger(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "ANSWERED",
                "EXPIRED",
                name="question_status",
                create_type=False,
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_group_question_publication",
        "group_questions",
        ["question_id", "group_id"],
        unique=True,
    )
    op.create_index(
        "ix_group_questions_group_status",
        "group_questions",
        ["group_id", "status"],
    )
    op.create_index(
        "ix_group_questions_expires_at", "group_questions", ["expires_at"]
    )

    op.add_column(
        "answers",
        sa.Column("group_question_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_answers_group_question_id",
        "answers",
        "group_questions",
        ["group_question_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_answers_group_question_id", "answers", ["group_question_id"]
    )
    op.create_index(
        "uq_daily_answer_per_user",
        "answers",
        ["question_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("group_id IS NULL"),
        sqlite_where=sa.text("group_id IS NULL"),
    )
    op.create_index(
        "uq_group_answer_per_user",
        "answers",
        ["question_id", "group_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("group_id IS NOT NULL"),
        sqlite_where=sa.text("group_id IS NOT NULL"),
    )
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


def downgrade() -> None:
    op.drop_index(
        "uq_library_reward_per_reference",
        table_name="rewards",
        postgresql_where=sa.text(
            "source IN ('DAILY_QUESTION', 'GROUP_QUESTION') "
            "AND reference_type IS NOT NULL AND reference_id IS NOT NULL"
        ),
    )
    op.drop_index("uq_group_answer_per_user", table_name="answers")
    op.drop_index("uq_daily_answer_per_user", table_name="answers")
    op.drop_index("ix_answers_group_question_id", table_name="answers")
    op.drop_constraint(
        "fk_answers_group_question_id", "answers", type_="foreignkey"
    )
    op.drop_column("answers", "group_question_id")
    op.drop_index("ix_group_questions_expires_at", table_name="group_questions")
    op.drop_index(
        "ix_group_questions_group_status", table_name="group_questions"
    )
    op.drop_index("uq_group_question_publication", table_name="group_questions")
    op.drop_table("group_questions")
