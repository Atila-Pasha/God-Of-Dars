"""Add knight guards and persistent health."""

import sqlalchemy as sa
from alembic import op

revision = "20261017_knights"
down_revision = "20261015_archer_midway"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_archers",
        sa.Column(
            "is_equipped", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    resource = sa.Enum(
        "COIN", "DIAMOND", "BANANA", name="resource_type", create_type=False
    )
    op.create_table(
        "knights",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("power", sa.Integer(), nullable=False),
        sa.Column("max_hp", sa.Integer(), nullable=False),
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
            "power >= 0 AND max_hp >= 1 AND purchase_price >= 0 AND upgrade_price >= 0 AND unlock_level >= 1",
            name="ck_knights_values",
        ),
    )
    op.create_index("ix_knights_name", "knights", ["name"], unique=True)
    op.create_table(
        "user_knights",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "knight_id",
            sa.BigInteger(),
            sa.ForeignKey("knights.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_hp", sa.Integer(), nullable=False),
        sa.Column(
            "is_equipped", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "level >= 1 AND current_hp >= 0", name="ck_user_knights_values"
        ),
    )
    op.create_index("uq_user_knights_user", "user_knights", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_user_knights_user", table_name="user_knights")
    op.drop_table("user_knights")
    op.drop_index("ix_knights_name", table_name="knights")
    op.drop_table("knights")
    op.drop_column("user_archers", "is_equipped")
