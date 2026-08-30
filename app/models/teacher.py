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
    from app.models.user_teacher import UserTeacher


class Teacher(Base):
    __tablename__ = "teachers"
    __table_args__ = (
        Index("ix_teachers_name", "name", unique=True),
        CheckConstraint("damage >= 0", name="ck_teachers_damage_non_negative"),
        CheckConstraint("max_hp >= 0", name="ck_teachers_max_hp_non_negative"),
        CheckConstraint(
            "purchase_price >= 0", name="ck_teachers_purchase_price_non_negative"
        ),
        CheckConstraint(
            "upgrade_price >= 0", name="ck_teachers_upgrade_price_non_negative"
        ),
        CheckConstraint("unlock_level >= 1", name="ck_teachers_unlock_level_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    damage: Mapped[int] = mapped_column(Integer, nullable=False)
    max_hp: Mapped[int] = mapped_column(Integer, nullable=False)
    purchase_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    upgrade_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unlock_level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    ability_text: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    owned_by_users: Mapped[list[UserTeacher]] = relationship(
        "UserTeacher", back_populates="teacher", passive_deletes=True
    )
