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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.castle import Castle


class Defense(Base):
    __tablename__ = "defenses"
    __table_args__ = (
        Index("ix_defenses_castle_id", "castle_id", unique=True),
        CheckConstraint("defense_power >= 0", name="ck_defenses_power_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    castle_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("castles.id", ondelete="CASCADE"), nullable=False
    )
    defense_power: Mapped[int] = mapped_column(BigInteger, nullable=False)
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

    castle: Mapped[Castle] = relationship("Castle", back_populates="defense")
