"""add API authentication sessions and idempotency storage"""

import sqlalchemy as sa
from alembic import op

revision = "20260911_api_auth"
down_revision = "20260908_load_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_users_level_id", "users", ["level", "id"])
    op.add_column(
        "notifications", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("provider_user_id", sa.BigInteger(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_user_id", name="uq_auth_identities_provider_user"
        ),
        sa.UniqueConstraint(
            "provider", "subject", name="uq_auth_identities_provider_subject"
        ),
    )
    op.create_index("ix_auth_identities_user_id", "auth_identities", ["user_id"])

    op.create_table(
        "auth_login_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("poll_secret_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=96), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="PENDING", nullable=False
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("app_version", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exchanged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auth_login_attempts_expires_at", "auth_login_attempts", ["expires_at"]
    )
    op.create_index(
        "ix_auth_login_attempts_state", "auth_login_attempts", ["state"], unique=True
    )
    op.create_index(
        "ix_auth_login_attempts_status_expires",
        "auth_login_attempts",
        ["status", "expires_at"],
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_refresh_token_hash", sa.String(length=64), nullable=True),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("app_version", sa.String(length=32), nullable=True),
        sa.Column("rotation_counter", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reuse_detected", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_index("ix_auth_sessions_family_id", "auth_sessions", ["family_id"])
    op.create_index(
        "ix_auth_sessions_refresh_hash",
        "auth_sessions",
        ["refresh_token_hash"],
        unique=True,
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

    op.create_table(
        "auth_refresh_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["auth_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auth_refresh_tokens_expires_at", "auth_refresh_tokens", ["expires_at"]
    )
    op.create_index(
        "ix_auth_refresh_tokens_hash",
        "auth_refresh_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_auth_refresh_tokens_session_id", "auth_refresh_tokens", ["session_id"]
    )

    op.create_table(
        "auth_audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auth_audit_events_session_id", "auth_audit_events", ["session_id"]
    )
    op.create_index(
        "ix_auth_audit_events_user_created",
        "auth_audit_events",
        ["user_id", "created_at"],
    )

    op.create_table(
        "api_idempotency_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("operation", sa.String(length=96), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="IN_PROGRESS", nullable=False
        ),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "operation", "idempotency_key", name="uq_api_idempotency_scope"
        ),
    )
    op.create_index(
        "ix_api_idempotency_expires_at", "api_idempotency_requests", ["expires_at"]
    )

    identity_table = sa.table(
        "auth_identities",
        sa.column("user_id", sa.BigInteger()),
        sa.column("provider", sa.String()),
        sa.column("subject", sa.String()),
        sa.column("provider_user_id", sa.BigInteger()),
        sa.column("profile", sa.JSON()),
    )
    user_table = sa.table(
        "users",
        sa.column("id", sa.BigInteger()),
        sa.column("telegram_user_id", sa.BigInteger()),
    )
    op.execute(
        identity_table.insert().from_select(
            ["user_id", "provider", "subject", "provider_user_id", "profile"],
            sa.select(
                user_table.c.id,
                sa.literal("telegram"),
                sa.cast(user_table.c.telegram_user_id, sa.String()),
                user_table.c.telegram_user_id,
                sa.cast(sa.literal("{}"), sa.JSON()),
            ),
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_api_idempotency_expires_at", table_name="api_idempotency_requests"
    )
    op.drop_table("api_idempotency_requests")
    op.drop_index("ix_auth_audit_events_user_created", table_name="auth_audit_events")
    op.drop_index("ix_auth_audit_events_session_id", table_name="auth_audit_events")
    op.drop_table("auth_audit_events")
    op.drop_index("ix_auth_refresh_tokens_session_id", table_name="auth_refresh_tokens")
    op.drop_index("ix_auth_refresh_tokens_hash", table_name="auth_refresh_tokens")
    op.drop_index("ix_auth_refresh_tokens_expires_at", table_name="auth_refresh_tokens")
    op.drop_table("auth_refresh_tokens")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_refresh_hash", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_family_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index(
        "ix_auth_login_attempts_status_expires", table_name="auth_login_attempts"
    )
    op.drop_index("ix_auth_login_attempts_state", table_name="auth_login_attempts")
    op.drop_index("ix_auth_login_attempts_expires_at", table_name="auth_login_attempts")
    op.drop_table("auth_login_attempts")
    op.drop_index("ix_auth_identities_user_id", table_name="auth_identities")
    op.drop_table("auth_identities")
    op.drop_column("notifications", "read_at")
    op.drop_index("ix_users_level_id", table_name="users")
