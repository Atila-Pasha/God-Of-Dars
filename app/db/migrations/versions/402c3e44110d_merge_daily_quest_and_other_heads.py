"""Merge daily quest and other heads

Revision ID: 402c3e44110d
Revises: 20260906_daily_quest_hardening, 4d5e6f7a8b9c
Create Date: 2026-09-06 15:17:53.961361

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '402c3e44110d'
down_revision: Union[str, Sequence[str], None] = ('20260906_daily_quest_hardening', '4d5e6f7a8b9c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
