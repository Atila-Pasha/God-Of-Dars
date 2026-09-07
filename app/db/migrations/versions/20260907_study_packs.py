"""move study packs to database"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260907_study_packs"
down_revision: str | Sequence[str] | None = "20260907_shield_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_packs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("reward_resource", sa.String(length=16), nullable=False),
        sa.Column("reward_amount", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("duration_minutes > 0", name="ck_study_packs_duration_positive"),
        sa.CheckConstraint("reward_amount >= 0", name="ck_study_packs_reward_non_negative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.bulk_insert(
        sa.table(
            "study_packs",
            sa.column("key", sa.String),
            sa.column("name", sa.String),
            sa.column("duration_minutes", sa.Integer),
            sa.column("reward_resource", sa.String),
            sa.column("reward_amount", sa.Integer),
            sa.column("is_active", sa.Boolean),
        ),
        [
            {"key": "half_hour", "name": "نیم‌ساعته", "duration_minutes": 30, "reward_resource": "COIN", "reward_amount": 100, "is_active": True},
            {"key": "one_hour", "name": "یک‌ساعته", "duration_minutes": 60, "reward_resource": "COIN", "reward_amount": 250, "is_active": True},
            {"key": "one_half_hour", "name": "یک‌ونیم‌ساعته", "duration_minutes": 90, "reward_resource": "DIAMOND", "reward_amount": 3, "is_active": True},
            {"key": "two_hours", "name": "دوساعته", "duration_minutes": 120, "reward_resource": "DIAMOND", "reward_amount": 5, "is_active": True},
        ],
    )


def downgrade() -> None:
    op.drop_table("study_packs")
