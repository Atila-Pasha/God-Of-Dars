"""add the buffet shield catalog and user inventory"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shields",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("reduction_percent", sa.Integer(), nullable=False),
        sa.Column(
            "flat_absorption", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("purchase_price", sa.BigInteger(), nullable=False),
        sa.Column("unlock_level", sa.Integer(), server_default="1", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reduction_percent >= 0 AND reduction_percent <= 100",
            name="ck_shields_reduction_percent_valid",
        ),
        sa.CheckConstraint(
            "flat_absorption >= 0", name="ck_shields_flat_absorption_non_negative"
        ),
        sa.CheckConstraint(
            "purchase_price >= 0", name="ck_shields_purchase_price_non_negative"
        ),
        sa.CheckConstraint(
            "unlock_level >= 1", name="ck_shields_unlock_level_positive"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shields_name", "shields", ["name"], unique=True)
    op.create_table(
        "user_shields",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("shield_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_equipped", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantity >= 0", name="ck_user_shields_quantity_non_negative"
        ),
        sa.ForeignKeyConstraint(["shield_id"], ["shields.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_shields_user_id", "user_shields", ["user_id"], unique=False
    )
    op.create_index(
        "ix_user_shields_shield_id", "user_shields", ["shield_id"], unique=False
    )
    op.create_index(
        "uq_user_shields_user_shield",
        "user_shields",
        ["user_id", "shield_id"],
        unique=True,
    )
    op.bulk_insert(
        sa.table(
            "shields",
            sa.column("name", sa.String),
            sa.column("reduction_percent", sa.Integer),
            sa.column("flat_absorption", sa.BigInteger),
            sa.column("purchase_price", sa.BigInteger),
            sa.column("unlock_level", sa.Integer),
            sa.column("description", sa.Text),
        ),
        [
            {
                "name": "سپر چوبی",
                "reduction_percent": 10,
                "flat_absorption": 5,
                "purchase_price": 150,
                "unlock_level": 1,
                "description": "یک سپر اقتصادی برای شروع بازی.",
            },
            {
                "name": "سپر آهنی",
                "reduction_percent": 25,
                "flat_absorption": 15,
                "purchase_price": 450,
                "unlock_level": 2,
                "description": "تعادل خوب بین قیمت و مقاومت.",
            },
            {
                "name": "سپر افسانه‌ای",
                "reduction_percent": 45,
                "flat_absorption": 35,
                "purchase_price": 1000,
                "unlock_level": 5,
                "description": "برای فرمانده‌هایی که دژشان ارزشمند است.",
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("uq_user_shields_user_shield", table_name="user_shields")
    op.drop_index("ix_user_shields_shield_id", table_name="user_shields")
    op.drop_index("ix_user_shields_user_id", table_name="user_shields")
    op.drop_table("user_shields")
    op.drop_index("ix_shields_name", table_name="shields")
    op.drop_table("shields")
