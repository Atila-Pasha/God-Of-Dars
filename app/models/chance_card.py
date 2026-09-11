from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ResourceType
from app.db.base import Base
from app.models.resource import RESOURCE_TYPE_ENUM


class ChanceCard(Base):
    __tablename__ = "chance_cards"
    __table_args__ = (Index("ix_chance_cards_user_claimed", "user_id", "is_claimed"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    resource_type: Mapped[ResourceType] = mapped_column(
        RESOURCE_TYPE_ENUM, nullable=False
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    captcha_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    captcha_answer: Mapped[str] = mapped_column(String(16), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_claimed: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
