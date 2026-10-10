"""Store a custom emoji for each shield and retain existing catalog icons."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261010_shield_emoji"
down_revision: str | Sequence[str] | None = "20261008_normalize_shields"
branch_labels = None
depends_on = None

EXISTING_ICONS = {
    "سپر زنگ تفریح": "5825861861278490879",
    "سپر آلودگی هوا": "5917839500750364054",
    "سپر محمدی": "5915796556606348792",
    "سپر کاظمی": "5917954648823570305",
    "سپر خسروپناه": "5915702157520150395",
}


def upgrade() -> None:
    op.add_column("shields", sa.Column("emoji", sa.String(length=32), nullable=True))
    connection = op.get_bind()
    for name, emoji_id in EXISTING_ICONS.items():
        connection.execute(
            sa.text("UPDATE shields SET emoji = :emoji WHERE name = :name"),
            {"emoji": emoji_id, "name": name},
        )


def downgrade() -> None:
    op.drop_column("shields", "emoji")
