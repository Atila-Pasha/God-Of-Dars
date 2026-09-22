"""seed balanced study packs and full-protection shields

Revision ID: 20260923_economy_catalog
Revises: 20260916_random_attack
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260923_economy_catalog"
down_revision: str | Sequence[str] | None = "20260916_random_attack"
branch_labels = None
depends_on = None


STUDY_PACKS = (
    ("quick_review", "مرور سریع", 15, "COIN", 40),
    ("half_hour", "مطالعه نیم‌ساعته", 30, "COIN", 90),
    ("one_hour", "مطالعه یک‌ساعته", 60, "COIN", 200),
    ("one_half_hour", "مطالعه یک‌ونیم‌ساعته", 90, "DIAMOND", 3),
    ("two_hours", "مطالعه دوساعته", 120, "DIAMOND", 5),
    ("three_hours", "مطالعه عمیق سه‌ساعته", 180, "DIAMOND", 8),
)

SHIELDS = (
    (
        "سپر زنگ تفریح",
        120,
        "COIN",
        1,
        30,
        "تا ۳۰ دقیقه جلوی هر حمله به دژ شما را می‌گیرد.",
    ),
    (
        "سپر کلاس بسته",
        300,
        "COIN",
        2,
        60,
        "تا ۶۰ دقیقه هیچ بازیکنی نمی‌تواند به شما حمله کند.",
    ),
    (
        "سپر نگهبان مدرسه",
        1_000,
        "DIAMOND",
        5,
        180,
        "سه ساعت مصونیت کامل در برابر حمله فراهم می‌کند.",
    ),
    (
        "سپر شب امتحان",
        3_000,
        "DIAMOND",
        10,
        360,
        "شش ساعت دژ شما را به‌طور کامل از حمله محافظت می‌کند.",
    ),
    (
        "سپر تعطیلی مدرسه",
        7_000,
        "DIAMOND",
        20,
        720,
        "دوازده ساعت امکان حمله به شما را غیرفعال می‌کند.",
    ),
    (
        "سپر دژ جاودان",
        15_000,
        "DIAMOND",
        30,
        1_440,
        "برای بیست‌وچهار ساعت جلوی تمام حملات به دژ شما را می‌گیرد.",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    for key, name, duration, resource, amount in STUDY_PACKS:
        bind.execute(
            sa.text(
                """
                INSERT INTO study_packs (
                    key, name, duration_minutes, reward_resource,
                    reward_amount, is_active
                ) VALUES (
                    :key, :name, :duration, :resource, :amount, TRUE
                )
                ON CONFLICT (key) DO UPDATE SET
                    name = EXCLUDED.name,
                    duration_minutes = EXCLUDED.duration_minutes,
                    reward_resource = EXCLUDED.reward_resource,
                    reward_amount = EXCLUDED.reward_amount,
                    is_active = TRUE
                """
            ),
            {
                "key": key,
                "name": name,
                "duration": duration,
                "resource": resource,
                "amount": amount,
            },
        )

    for name, price, resource, level, duration, description in SHIELDS:
        bind.execute(
            sa.text(
                """
                INSERT INTO shields (
                    name, reduction_percent, flat_absorption, purchase_price,
                    purchase_resource, unlock_level, duration_minutes,
                    description, is_active
                ) VALUES (
                    :name, 0, 0, :price, :resource, :level, :duration,
                    :description, TRUE
                )
                ON CONFLICT (name) DO UPDATE SET
                    reduction_percent = 0,
                    flat_absorption = 0,
                    purchase_price = EXCLUDED.purchase_price,
                    purchase_resource = EXCLUDED.purchase_resource,
                    unlock_level = EXCLUDED.unlock_level,
                    duration_minutes = EXCLUDED.duration_minutes,
                    description = EXCLUDED.description,
                    is_active = TRUE
                """
            ),
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
    # Catalog rows may already be referenced by live user state. A destructive
    # downgrade would either fail or erase purchased protection.
    pass
