from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
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
    from app.models.shield import Shield
    from app.models.user import User


class UserShield(Base):
    __tablename__ = "user_shields"
    __table_args__ = (
        Index("ix_user_shields_user_id", "user_id"),
        Index("ix_user_shields_shield_id", "shield_id"),
        Index("uq_user_shields_user_shield", "user_id", "shield_id", unique=True),
        CheckConstraint("quantity >= 0", name="ck_user_shields_quantity_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    shield_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shields.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_equipped: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
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

    user: Mapped[User] = relationship("User", back_populates="shields")
    shield: Mapped[Shield] = relationship("Shield", back_populates="owned_by_users")
