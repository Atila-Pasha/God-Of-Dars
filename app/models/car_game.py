"""Persistent, server-scored runs of the three-lane car game."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CarGame(Base):
    __tablename__ = "car_games"
    __table_args__ = (
        CheckConstraint("lane BETWEEN 0 AND 2", name="ck_car_game_lane"),
        CheckConstraint(
            "tick >= 0 AND coin >= 0 AND diamond >= 0", name="ck_car_game_counts"
        ),
        Index("ix_car_games_user_status", "user_id", "status"),
        Index("ix_car_games_due", "status", "next_tick_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")
    seed: Mapped[int] = mapped_column(nullable=False)
    lane: Mapped[int] = mapped_column(nullable=False, default=1)
    tick: Mapped[int] = mapped_column(nullable=False, default=0)
    coin: Mapped[int] = mapped_column(nullable=False, default=0)
    diamond: Mapped[int] = mapped_column(nullable=False, default=0)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
