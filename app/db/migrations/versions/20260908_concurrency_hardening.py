"""harden attack and study state transitions for concurrent workers"""

import sqlalchemy as sa
from alembic import op

revision = "20260908_concurrency_hardening"
down_revision = "20260907_daily_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE attack_status ADD VALUE IF NOT EXISTS 'PROCESSING'")
        op.execute("ALTER TYPE attack_status ADD VALUE IF NOT EXISTS 'FAILED'")

    op.add_column(
        "attacks",
        sa.Column("processing_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_attacks_status_resolve_at",
        "attacks",
        ["status", "resolve_at"],
        unique=False,
    )
    op.create_index(
        "uq_study_sessions_active_per_user",
        "study_sessions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("completed_at IS NULL"),
        sqlite_where=sa.text("completed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_study_sessions_active_per_user", table_name="study_sessions")
    op.drop_index("ix_attacks_status_resolve_at", table_name="attacks")
    op.drop_column("attacks", "processing_at")
