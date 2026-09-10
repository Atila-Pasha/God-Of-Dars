"""add durable idempotent Telegram notification outbox"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260908_notification_outbox"
down_revision = "20260908_attack_retry_and_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DO $$ BEGIN "
            "CREATE TYPE notification_status AS ENUM "
            "('PENDING', 'PROCESSING', 'SENT', 'FAILED'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )
    status_type = (
        postgresql.ENUM(
            "PENDING", "PROCESSING", "SENT", "FAILED",
            name="notification_status",
            create_type=False,
        )
        if bind.dialect.name == "postgresql"
        else sa.String(16)
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("notification_type", sa.String(length=64), nullable=False),
        sa.Column("recipient_user_id", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", status_type, nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.CheckConstraint("attempts >= 0", name="ck_notifications_attempts_non_negative"),
    )
    op.create_index(
        "ix_notifications_status_next_attempt",
        "notifications",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_status_next_attempt", table_name="notifications")
    op.drop_table("notifications")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS notification_status")
