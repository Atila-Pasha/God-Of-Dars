from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChanceBoxAttempt(Base):
    __tablename__ = "chance_box_attempts"
    __table_args__ = (UniqueConstraint("box_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    box_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chance_boxes.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
