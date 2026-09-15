from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RandomAttackSelection(Base):
    """One durable random-opponent choice per attacker."""

    __tablename__ = "random_attack_selections"
    __table_args__ = (
        Index("ix_random_attack_selections_expires_at", "expires_at"),
        Index("ix_random_attack_selections_target_id", "target_id"),
        CheckConstraint("version > 0", name="ck_random_attack_selection_version"),
        CheckConstraint(
            "reroll_count >= 0", name="ck_random_attack_selection_reroll_count"
        ),
    )

    attacker_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    target_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Owned UserTeacher ids are immutable enough for a short-lived preview and
    # prevent a forged callback from selecting a different teacher.
    teacher_ids: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    reroll_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
