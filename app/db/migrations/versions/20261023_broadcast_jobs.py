"""Persist broadcast progress outside the admin update handler."""

import sqlalchemy as sa
from alembic import op

revision = "20261023_broadcast_jobs"
down_revision = "20261023_real_rank_opponents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broadcast_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("admin_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("text", sa.Text()),
        sa.Column("caption", sa.Text()),
        sa.Column("photo_data", sa.LargeBinary()),
        sa.Column("photo_file_id", sa.String(512)),
        sa.Column("max_user_id", sa.BigInteger(), nullable=False),
        sa.Column("last_user_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("report_sent_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "total >= 0 AND sent >= 0 AND failed >= 0", name="ck_broadcast_jobs_counts"
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_broadcast_jobs_active ON broadcast_jobs ((1)) "
        "WHERE status IN ('PENDING', 'RUNNING')"
    )
    op.create_index("ix_broadcast_jobs_status_id", "broadcast_jobs", ["status", "id"])


def downgrade() -> None:
    op.drop_index("ix_broadcast_jobs_status_id", table_name="broadcast_jobs")
    op.execute("DROP INDEX uq_broadcast_jobs_active")
    op.drop_table("broadcast_jobs")
