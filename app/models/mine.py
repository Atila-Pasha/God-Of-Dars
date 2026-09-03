from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class Mine(Base):
    __tablename__ = "mines"
    __table_args__ = (
        Index("ix_mines_user_id", "user_id", unique=True),
        CheckConstraint("level >= 1", name="ck_mines_level_positive"),
        CheckConstraint("today_coin >= 0", name="ck_mines_today_coin_non_negative"),
        CheckConstraint(
            "today_diamond >= 0", name="ck_mines_today_diamond_non_negative"
        ),
        CheckConstraint("today_banana >= 0", name="ck_mines_today_banana_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    last_collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    today: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    today_coin: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    today_diamond: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    today_banana: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
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

    user: Mapped[User] = relationship("User", back_populates="mine")
