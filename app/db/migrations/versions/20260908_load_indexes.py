"""add indexes for worker claims and case-insensitive lookups"""

import sqlalchemy as sa
from alembic import op

revision = "20260908_load_indexes"
down_revision = "20260908_notification_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_attacks_failed_next_retry",
        "attacks",
        ["next_retry_at", "id"],
        postgresql_where="status = 'FAILED'",
    )
    op.create_index(
        "ix_attacks_processing_at",
        "attacks",
        ["processing_at", "id"],
        postgresql_where="status = 'PROCESSING'",
    )
    op.create_index(
        "ix_notifications_due_order",
        "notifications",
        ["created_at", "id"],
        postgresql_where="status IN ('PENDING', 'FAILED')",
    )
    op.create_index(
        "ix_notifications_processing_at",
        "notifications",
        ["processing_at", "id"],
        postgresql_where="status = 'PROCESSING'",
    )
    op.create_index(
        "ix_users_username_lower",
        "users",
        [sa.text("lower(username)")],
        postgresql_using="btree",
    )
    op.create_index(
        "ix_teachers_name_lower",
        "teachers",
        [sa.text("lower(name)")],
        postgresql_using="btree",
    )


def downgrade() -> None:
    op.drop_index("ix_teachers_name_lower", table_name="teachers")
    op.drop_index("ix_users_username_lower", table_name="users")
    op.drop_index("ix_notifications_processing_at", table_name="notifications")
    op.drop_index("ix_notifications_due_order", table_name="notifications")
    op.drop_index("ix_attacks_processing_at", table_name="attacks")
    op.drop_index("ix_attacks_failed_next_retry", table_name="attacks")
