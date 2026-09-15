"""balance and guarantee a starter teacher

Revision ID: 20260914_starter_teacher
Revises: 20260914_economy_baseline
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_starter_teacher"
down_revision: str | Sequence[str] | None = "20260914_economy_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Correct only the exact known pre-balance row. Any administrator edit to
    # its price, resource, level, or upgrade cost makes this update a no-op.
    bind.execute(
        sa.text(
            """
            UPDATE teachers
            SET purchase_price = 200, upgrade_price = 20
            WHERE name = :name
              AND unlock_level = 1
              AND purchase_resource = 'COIN'
              AND purchase_price = 10000
              AND upgrade_price = 10
            """
        ),
        {"name": "فراهانی"},
    )

    has_starter = bind.scalar(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1 FROM teachers
                WHERE is_active IS TRUE AND unlock_level <= 1
            )
            """
        )
    )
    if has_starter:
        return

    bind.execute(
        sa.text(
            """
            INSERT INTO teachers (
                name, damage, max_hp, purchase_price, purchase_resource,
                upgrade_price, unlock_level, ability_text, description, is_active
            ) VALUES (
                :name, 35, 80, 200, 'COIN', 20, 1,
                :ability, :description, TRUE
            )
            """
        ),
        {
            "name": "دبیر آغازین",
            "ability": "آماده برای نخستین نبردهای مدرسه",
            "description": "دبیر متعادل سطح یک برای شروع مسیر بازی.",
        },
    )


def downgrade() -> None:
    # The row may be owned or edited after migration; destructive rollback is
    # intentionally avoided.
    pass
