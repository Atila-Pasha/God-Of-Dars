"""Update shield descriptions to match the arsenal banner."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_shield_descriptions"
down_revision: str | Sequence[str] | None = "20261008_box_sticker"
branch_labels = None
depends_on = None

DESCRIPTIONS = {
    "سپر زنگ تفریح": "تا 30 دقیقه جلوی هر حمله به دژ شما را می‌گیرد.",
    "سپر آلودگی هوا": "سه ساعت مصونیت کامل در برابر حمله فراهم می‌کند.",
    "سپر محمدی": (
        "6 ساعت دژ شما را به‌طور کامل از حمله محافظت می‌کند. "
        "در صورت حمله از سمت شما سرعت اتمام سپر 2x حساب میشه."
    ),
    "سپر کاظمی": (
        "12 ساعت امکان حمله به شما را غیرفعال می‌کند. "
        "در صورت حمله موسوی و کاظم قلمچی سپر توانایی دفاع ندارد."
    ),
    "سپر خسروپناه": (
        "به مدت 24 ساعت جلوی تمام حملات به دژ شما را می‌گیرد. "
        "هیچ حمله ای از این سپر رد نمیشه !"
    ),
}


def upgrade() -> None:
    connection = op.get_bind()
    for name, description in DESCRIPTIONS.items():
        connection.execute(
            sa.text("UPDATE shields SET description = :description WHERE name = :name"),
            {"name": name, "description": description},
        )


def downgrade() -> None:
    pass
