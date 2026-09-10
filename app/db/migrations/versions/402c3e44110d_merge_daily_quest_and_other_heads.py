"""Merge daily quest and other heads

Revision ID: 402c3e44110d
Revises: 20260906_daily_quest_hardening, 4d5e6f7a8b9c
Create Date: 2026-09-06 15:17:53.961361

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '402c3e44110d'
down_revision: str | Sequence[str] | None = ('20260906_daily_quest_hardening', '4d5e6f7a8b9c')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
