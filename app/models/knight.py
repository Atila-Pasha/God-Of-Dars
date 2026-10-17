"""Purchasable castle guards and their persistent health."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ResourceType
from app.db.base import Base
from app.models.resource import RESOURCE_TYPE_ENUM


class Knight(Base):
    __tablename__ = "knights"
    __table_args__ = (
        Index("ix_knights_name", "name", unique=True),
        CheckConstraint(
            "power >= 0 AND max_hp >= 1 AND purchase_price >= 0 AND upgrade_price >= 0 AND unlock_level >= 1",
            name="ck_knights_values",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    power: Mapped[int] = mapped_column(Integer, nullable=False)
    max_hp: Mapped[int] = mapped_column(Integer, nullable=False)
    purchase_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purchase_resource: Mapped[ResourceType] = mapped_column(
        RESOURCE_TYPE_ENUM,
        nullable=False,
        default=ResourceType.COIN,
        server_default="COIN",
    )
    upgrade_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unlock_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(Text)
    emoji: Mapped[str | None] = mapped_column(String(32))
    sticker: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    owners: Mapped[list["UserKnight"]] = relationship(
        "UserKnight", back_populates="knight"
    )


class UserKnight(Base):
    __tablename__ = "user_knights"
    __table_args__ = (
        Index("uq_user_knights_user", "user_id", unique=True),
        CheckConstraint(
            "level >= 1 AND current_hp >= 0", name="ck_user_knights_values"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    knight_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knights.id", ondelete="RESTRICT"), nullable=False
    )
    level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    current_hp: Mapped[int] = mapped_column(Integer, nullable=False)
    is_equipped: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    knight: Mapped[Knight] = relationship("Knight", back_populates="owners")
