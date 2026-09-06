"""merge the teacher description and main migration branches"""

from collections.abc import Sequence

revision = "4d5e6f7a8b9c"
down_revision: tuple[str, str] = ("2c3d4e5f6a7b", "3c4d5e6f7a8b")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
