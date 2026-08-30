from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.defense import Defense
    from app.models.user import User


class Castle(Base):
    __tablename__ = "castles"
    __table_args__ = (
        Index("ix_castles_user_id", "user_id", unique=True),
        CheckConstraint("level >= 1", name="ck_castles_level_positive"),
        CheckConstraint("strength >= 0", name="ck_castles_strength_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    strength: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship("User", back_populates="castle")
    defense: Mapped[Defense | None] = relationship(
        "Defense", back_populates="castle", uselist=False, cascade="all, delete-orphan"
    )
