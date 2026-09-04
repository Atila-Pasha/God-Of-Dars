"""merge the shields/mines branch with the required-channels branch"""

from collections.abc import Sequence

from alembic import op

revision = "d4e5f6a7b8c9"
down_revision: tuple[str, str] = ("b2c3d4e5f6a7", "c8d9e0f1a2b3")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
