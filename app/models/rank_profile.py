from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RankProfile(Base):
    __tablename__ = "rank_profiles"
    __table_args__ = (
        Index("ix_rank_profiles_season_cups", "season_start", "cups"),
        CheckConstraint("cups >= 0", name="ck_rank_profiles_cups"),
        CheckConstraint(
            "daily_attacks BETWEEN 0 AND 20", name="ck_rank_profiles_daily_attacks"
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    season_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    cups: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    best_cups: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    wins: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    losses: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    daily_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    daily_attacks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
