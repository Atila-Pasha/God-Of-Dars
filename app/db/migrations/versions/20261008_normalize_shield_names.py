"""Normalize existing short shield names to the names shown in the arsenal."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_normalize_shields"
down_revision: str | Sequence[str] | None = "20261008_shield_daily_limit"
branch_labels = None
depends_on = None

SHIELDS = (
    ("زنگ تفریح", "سپر زنگ تفریح", 2, "تا 30 دقیقه جلوی هر حمله به دژ شما را می‌گیرد."),
    (
        "آلودگی هوا",
        "سپر آلودگی هوا",
        1,
        "سه ساعت مصونیت کامل در برابر حمله فراهم می‌کند.",
    ),
    (
        "محمدی",
        "سپر محمدی",
        None,
        "6 ساعت دژ شما را به‌طور کامل از حمله محافظت می‌کند. "
        "در صورت حمله از سمت شما سرعت اتمام سپر 2x حساب میشه.",
    ),
    (
        "کاظمی",
        "سپر کاظمی",
        None,
        "12 ساعت امکان حمله به شما را غیرفعال می‌کند. "
        "در صورت حمله موسوی و کاظم قلمچی سپر توانایی دفاع ندارد.",
    ),
    (
        "خسروپناه",
        "سپر خسروپناه",
        None,
        "به مدت 24 ساعت جلوی تمام حملات به دژ شما را می‌گیرد. "
        "هیچ حمله ای از این سپر رد نمیشه !",
    ),
)


def upgrade() -> None:
    connection = op.get_bind()
    for short_name, full_name, daily_limit, description in SHIELDS:
        connection.execute(
            sa.text(
                "UPDATE shields SET name = :full_name, description = :description, "
                "daily_limit = COALESCE(daily_limit, :daily_limit) "
                "WHERE name = :short_name "
                "AND NOT EXISTS (SELECT 1 FROM shields WHERE name = :full_name)"
            ),
            {
                "short_name": short_name,
                "full_name": full_name,
                "daily_limit": daily_limit,
                "description": description,
            },
        )
        connection.execute(
            sa.text("UPDATE shields SET is_active = FALSE WHERE name = :short_name"),
            {"short_name": short_name},
        )


def downgrade() -> None:
    pass
