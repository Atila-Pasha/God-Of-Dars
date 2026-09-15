"""remove storage used only by the retired HTTP API

Revision ID: 20260916_remove_api
Revises: 20260916_leaderboard_indexes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_remove_api"
down_revision: str | Sequence[str] | None = "20260916_leaderboard_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Child tables must be removed before their referenced auth session.
    op.drop_table("api_idempotency_requests")
    op.drop_table("auth_audit_events")
    op.drop_table("auth_refresh_tokens")
    op.drop_table("auth_sessions")
    op.drop_table("auth_login_attempts")
    op.drop_table("auth_identities")


def downgrade() -> None:
    # Downgrade restores the schema, not authentication/audit data deleted by
    # the upgrade. Back up the database before deploying this revision if that
    # retired API data must be retained.
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
        "ix_auth_login_attempts_state",
        "auth_login_attempts",
        ["state"],
        unique=True,
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
            "status",
            sa.String(length=16),
            server_default="IN_PROGRESS",
            nullable=False,
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
