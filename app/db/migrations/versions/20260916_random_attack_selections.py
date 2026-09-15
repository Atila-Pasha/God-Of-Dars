"""persist random attack opponents and rerolls

Revision ID: 20260916_random_attack
Revises: 20260916_remove_api
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_random_attack"
down_revision: str | Sequence[str] | None = "20260916_remove_api"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "random_attack_selections",
        sa.Column("attacker_id", sa.BigInteger(), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("teacher_ids", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("reroll_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("version > 0", name="ck_random_attack_selection_version"),
        sa.CheckConstraint(
            "reroll_count >= 0", name="ck_random_attack_selection_reroll_count"
        ),
        sa.ForeignKeyConstraint(["attacker_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("attacker_id"),
    )
    op.create_index(
        "ix_random_attack_selections_expires_at",
        "random_attack_selections",
        ["expires_at"],
    )
    op.create_index(
        "ix_random_attack_selections_target_id",
        "random_attack_selections",
        ["target_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_random_attack_selections_target_id",
        table_name="random_attack_selections",
    )
    op.drop_index(
        "ix_random_attack_selections_expires_at",
        table_name="random_attack_selections",
    )
    op.drop_table("random_attack_selections")
