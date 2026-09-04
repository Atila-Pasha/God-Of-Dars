"""merge the presentation-fields and chance-expiry migration heads"""

from collections.abc import Sequence

revision: str = "2b3c4d5e6f7a"
down_revision: tuple[str, str] = ("1a2b3c4d5e6f", "a7b8c9d0e1f2")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
