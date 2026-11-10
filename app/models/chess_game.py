"""Persistent chess matches, including move history for repetition rules."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChessGame(Base):
    __tablename__ = "chess_games"
    __table_args__ = (
        CheckConstraint("stake_amount >= 0", name="ck_chess_stake_nonnegative"),
        Index("ix_chess_status_deadline", "status", "deadline_at"),
        Index("ix_chess_challenger_status", "challenger_id", "status"),
        Index("ix_chess_opponent_status", "opponent_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    challenger_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    opponent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    stake_type: Mapped[str | None] = mapped_column(String(16))
    stake_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="invited")
    moves: Mapped[str] = mapped_column(Text, nullable=False, default="")
    turn_id: Mapped[int | None] = mapped_column(BigInteger)
    winner_id: Mapped[int | None] = mapped_column(BigInteger)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escrowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    challenger_message_id: Mapped[int | None] = mapped_column(BigInteger)
    opponent_message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
