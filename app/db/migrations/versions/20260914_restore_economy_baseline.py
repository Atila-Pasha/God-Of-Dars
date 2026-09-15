"""restore the minimum bot economy catalog

Revision ID: 20260914_economy_baseline
Revises: 20260911_api_auth
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_economy_baseline"
down_revision: str | Sequence[str] | None = "20260911_api_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Restore only missing built-in rows; never overwrite admin changes."""
    bind = op.get_bind()

    study_packs = sa.table(
        "study_packs",
        sa.column("key", sa.String),
        sa.column("name", sa.String),
        sa.column("duration_minutes", sa.Integer),
        sa.column("reward_resource", sa.String),
        sa.column("reward_amount", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    existing_pack_keys = set(bind.execute(sa.select(study_packs.c.key)).scalars())
    default_packs = (
        ("half_hour", "مطالعه نیم‌ساعته", 30, "COIN", 100),
        ("one_hour", "مطالعه یک‌ساعته", 60, "COIN", 250),
        ("one_half_hour", "مطالعه یک‌ونیم‌ساعته", 90, "DIAMOND", 3),
        ("two_hours", "مطالعه دوساعته", 120, "DIAMOND", 5),
    )
    missing_packs = [
        {
            "key": key,
            "name": name,
            "duration_minutes": duration,
            "reward_resource": resource,
            "reward_amount": amount,
            "is_active": True,
        }
        for key, name, duration, resource, amount in default_packs
        if key not in existing_pack_keys
    ]
    if missing_packs:
        op.bulk_insert(study_packs, missing_packs)

    shields = sa.table(
        "shields",
        sa.column("name", sa.String),
        sa.column("reduction_percent", sa.Integer),
        sa.column("flat_absorption", sa.BigInteger),
        sa.column("purchase_price", sa.BigInteger),
        sa.column(
            "purchase_resource",
            sa.Enum(
                "COIN",
                "DIAMOND",
                "BANANA",
                name="resource_type",
                create_type=False,
            ),
        ),
        sa.column("unlock_level", sa.Integer),
        sa.column("duration_minutes", sa.Integer),
        sa.column("description", sa.Text),
        sa.column("is_active", sa.Boolean),
    )
    existing_shield_names = set(bind.execute(sa.select(shields.c.name)).scalars())
    default_shields = (
        (
            "سپر چوبی",
            10,
            5,
            150,
            "COIN",
            1,
            60,
            "۱۰٪ کاهش آسیب و ۵ واحد جذب ثابت برای شروع بازی.",
        ),
        (
            "سپر آهنی",
            25,
            15,
            450,
            "COIN",
            2,
            60,
            "۲۵٪ کاهش آسیب و ۱۵ واحد جذب ثابت.",
        ),
        (
            "سپر افسانه‌ای",
            45,
            35,
            1_000,
            "COIN",
            5,
            60,
            "۴۵٪ کاهش آسیب و ۳۵ واحد جذب ثابت برای نبردهای سنگین.",
        ),
    )
    missing_shields = [
        {
            "name": name,
            "reduction_percent": reduction,
            "flat_absorption": absorption,
            "purchase_price": price,
            "purchase_resource": resource,
            "unlock_level": unlock_level,
            "duration_minutes": duration,
            "description": description,
            "is_active": True,
        }
        for (
            name,
            reduction,
            absorption,
            price,
            resource,
            unlock_level,
            duration,
            description,
        ) in default_shields
        if name not in existing_shield_names
    ]
    if missing_shields:
        op.bulk_insert(shields, missing_shields)


def downgrade() -> None:
    # Catalog rows can be purchased or edited after upgrade. Removing them on
    # downgrade could violate references or destroy admin-owned changes.
    pass
