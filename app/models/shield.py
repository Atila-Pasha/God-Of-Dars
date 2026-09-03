from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user_shield import UserShield


class Shield(Base):
    __tablename__ = "shields"
    __table_args__ = (
        Index("ix_shields_name", "name", unique=True),
        CheckConstraint(
            "reduction_percent >= 0 AND reduction_percent <= 100",
            name="ck_shields_reduction_percent_valid",
        ),
        CheckConstraint(
            "flat_absorption >= 0", name="ck_shields_flat_absorption_non_negative"
        ),
        CheckConstraint(
            "purchase_price >= 0", name="ck_shields_purchase_price_non_negative"
        ),
        CheckConstraint("unlock_level >= 1", name="ck_shields_unlock_level_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    reduction_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    flat_absorption: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    purchase_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unlock_level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
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

    owned_by_users: Mapped[list[UserShield]] = relationship(
        "UserShield", back_populates="shield", passive_deletes=True
    )
