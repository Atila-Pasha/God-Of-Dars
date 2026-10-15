"""Add purchasable archers, consumable arrow packs and battle reports."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261015_archers"
down_revision: str | Sequence[str] | None = "20261010_shield_emoji"
branch_labels = None
depends_on = None


def upgrade() -> None:
    resource = sa.Enum(
        "COIN", "DIAMOND", "BANANA", name="resource_type", create_type=False
    )
    op.create_table(
        "archers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("power", sa.Integer(), nullable=False),
        sa.Column("purchase_price", sa.BigInteger(), nullable=False),
        sa.Column("purchase_resource", resource, nullable=False, server_default="COIN"),
        sa.Column("upgrade_price", sa.BigInteger(), nullable=False),
        sa.Column("unlock_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("description", sa.Text()),
        sa.Column("emoji", sa.String(32)),
        sa.Column("sticker", sa.String(255)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "power >= 0 AND purchase_price >= 0 AND upgrade_price >= 0 AND unlock_level >= 1",
            name="ck_archers_values",
        ),
    )
    op.create_index("ix_archers_name", "archers", ["name"], unique=True)
    op.create_table(
        "user_archers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "archer_id",
            sa.BigInteger(),
            sa.ForeignKey("archers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("level >= 1", name="ck_user_archers_level"),
    )
    op.create_index("uq_user_archers_user", "user_archers", ["user_id"], unique=True)
    op.create_index(
        "uq_user_archers_user_archer",
        "user_archers",
        ["user_id", "archer_id"],
        unique=True,
    )
    op.create_table(
        "arrow_packs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("power", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("purchase_price", sa.BigInteger(), nullable=False),
        sa.Column("purchase_resource", resource, nullable=False, server_default="COIN"),
        sa.Column("unlock_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "power >= 0 AND quantity >= 1 AND purchase_price >= 0 AND unlock_level >= 1",
            name="ck_arrow_packs_values",
        ),
    )
    op.create_index("ix_arrow_packs_name", "arrow_packs", ["name"], unique=True)
    op.create_table(
        "user_arrows",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pack_id",
            sa.BigInteger(),
            sa.ForeignKey("arrow_packs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_equipped", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.CheckConstraint("quantity >= 0", name="ck_user_arrows_quantity"),
    )
    op.create_index(
        "uq_user_arrows_user_pack", "user_arrows", ["user_id", "pack_id"], unique=True
    )
    for name, type_, default in (
        ("archer_name_snapshot", sa.String(100), None),
        ("archer_emoji_snapshot", sa.String(32), None),
        ("archer_sticker_snapshot", sa.String(255), None),
        ("arrow_name_snapshot", sa.String(100), None),
        ("result_archer_injury", sa.Integer(), "0"),
    ):
        op.add_column(
            "attacks",
            sa.Column(name, type_, nullable=default is None, server_default=default),
        )


def downgrade() -> None:
    for name in (
        "result_archer_injury",
        "arrow_name_snapshot",
        "archer_sticker_snapshot",
        "archer_emoji_snapshot",
        "archer_name_snapshot",
    ):
        op.drop_column("attacks", name)
    op.drop_index("uq_user_arrows_user_pack", table_name="user_arrows")
    op.drop_table("user_arrows")
    op.drop_index("ix_arrow_packs_name", table_name="arrow_packs")
    op.drop_table("arrow_packs")
    op.drop_index("uq_user_archers_user_archer", table_name="user_archers")
    op.drop_index("uq_user_archers_user", table_name="user_archers")
    op.drop_table("user_archers")
    op.drop_index("ix_archers_name", table_name="archers")
    op.drop_table("archers")
