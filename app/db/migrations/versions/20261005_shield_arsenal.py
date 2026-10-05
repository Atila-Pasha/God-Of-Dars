"""Replace the purchasable shield catalog with the school arsenal.

Keep referenced legacy rows inactive so existing timed protection and foreign
keys survive the change. Unreferenced legacy rows are removed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_shield_arsenal"
down_revision: str | Sequence[str] | None = "20261003_attack_launch_message"
branch_labels = None
depends_on = None

SHIELDS = (
    (
        "سپر زنگ تفریح",
        120,
        "COIN",
        1,
        30,
        "تا 30 دقیقه جلوی هر حمله به دژ شما را می‌گیرد.",
    ),
    (
        "سپر آلودگی هوا",
        1000,
        "DIAMOND",
        5,
        180,
        "سه ساعت مصونیت کامل در برابر حمله فراهم می‌کند.",
    ),
    (
        "سپر محمدی",
        3000,
        "DIAMOND",
        10,
        360,
        "6 ساعت دژ شما را به‌طور کامل از حمله محافظت می‌کند.",
    ),
    (
        "سپر کاظمی",
        7000,
        "DIAMOND",
        20,
        720,
        "12 ساعت جلوی حمله را می‌گیرد؛ موسوی و کاظم قلمچی از آن عبور می‌کنند.",
    ),
    (
        "سپر خسروپناه",
        15000,
        "DIAMOND",
        30,
        1440,
        "24 ساعت جلوی تمام حملات به دژ شما را می‌گیرد.",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    names = tuple(item[0] for item in SHIELDS)
    bind.execute(
        sa.text(
            "DELETE FROM shields WHERE name NOT IN :names AND id NOT IN (SELECT shield_id FROM user_shields)"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"names": names},
    )
    bind.execute(
        sa.text(
            "UPDATE shields SET is_active = FALSE WHERE name NOT IN :names"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"names": names},
    )
    for name, price, resource, level, duration, description in SHIELDS:
        bind.execute(
            sa.text("""
            INSERT INTO shields (name, reduction_percent, flat_absorption,
                purchase_price, purchase_resource, unlock_level,
                duration_minutes, description, is_active)
            VALUES (:name, 0, 0, :price, :resource, :level, :duration,
                :description, TRUE)
            ON CONFLICT (name) DO UPDATE SET
                reduction_percent = 0, flat_absorption = 0,
                purchase_price = EXCLUDED.purchase_price,
                purchase_resource = EXCLUDED.purchase_resource,
                unlock_level = EXCLUDED.unlock_level,
                duration_minutes = EXCLUDED.duration_minutes,
                description = EXCLUDED.description, is_active = TRUE
        """),
            {
                "name": name,
                "price": price,
                "resource": resource,
                "level": level,
                "duration": duration,
                "description": description,
            },
        )


def downgrade() -> None:
    # Live purchases may reference these rows; reverting the catalog is unsafe.
    pass
