"""add bounded attack retries and attack ledger idempotency"""

from alembic import op

revision = "20260908_attack_retry_and_ledger"
down_revision = "20260908_concurrency_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE attacks ADD COLUMN IF NOT EXISTS "
        "failed_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "ALTER TABLE attacks ADD COLUMN IF NOT EXISTS "
        "retry_count INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE attacks ADD COLUMN IF NOT EXISTS "
        "next_retry_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute("ALTER TABLE attacks ADD COLUMN IF NOT EXISTS last_error VARCHAR(500)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_attack_transaction_per_resource "
        "ON transactions (user_id, resource_type, reference_type, reference_id) "
        "WHERE reference_type = 'ATTACK' AND reference_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_attack_transaction_per_resource")
    op.execute("ALTER TABLE attacks DROP COLUMN IF EXISTS last_error")
    op.execute("ALTER TABLE attacks DROP COLUMN IF EXISTS next_retry_at")
    op.execute("ALTER TABLE attacks DROP COLUMN IF EXISTS retry_count")
    op.execute("ALTER TABLE attacks DROP COLUMN IF EXISTS failed_at")
