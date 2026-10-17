from __future__ import annotations

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


class Archer(Base):
    __tablename__ = "archers"
    __table_args__ = (
        Index("ix_archers_name", "name", unique=True),
        CheckConstraint(
            "power >= 0 AND purchase_price >= 0 AND upgrade_price >= 0 AND unlock_level >= 1",
            name="ck_archers_values",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    power: Mapped[int] = mapped_column(Integer, nullable=False)
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
    owners: Mapped[list[UserArcher]] = relationship(
        "UserArcher", back_populates="archer"
    )


class UserArcher(Base):
    __tablename__ = "user_archers"
    __table_args__ = (
        Index("uq_user_archers_user", "user_id", unique=True),
        Index("uq_user_archers_user_archer", "user_id", "archer_id", unique=True),
        CheckConstraint("level >= 1", name="ck_user_archers_level"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    archer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("archers.id", ondelete="RESTRICT"), nullable=False
    )
    level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    is_equipped: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    archer: Mapped[Archer] = relationship("Archer", back_populates="owners")


class ArrowPack(Base):
    __tablename__ = "arrow_packs"
    __table_args__ = (
        Index("ix_arrow_packs_name", "name", unique=True),
        CheckConstraint(
            "power >= 0 AND quantity >= 1 AND purchase_price >= 0 AND unlock_level >= 1",
            name="ck_arrow_packs_values",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    power: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    purchase_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purchase_resource: Mapped[ResourceType] = mapped_column(
        RESOURCE_TYPE_ENUM,
        nullable=False,
        default=ResourceType.COIN,
        server_default="COIN",
    )
    unlock_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserArrow(Base):
    __tablename__ = "user_arrows"
    __table_args__ = (
        Index("uq_user_arrows_user_pack", "user_id", "pack_id", unique=True),
        CheckConstraint("quantity >= 0", name="ck_user_arrows_quantity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    pack_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("arrow_packs.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_equipped: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    pack: Mapped[ArrowPack] = relationship("ArrowPack")
