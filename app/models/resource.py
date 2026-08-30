from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ResourceType
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


RESOURCE_TYPE_ENUM = SAEnum(ResourceType, name="resource_type")


class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = (
        Index("ix_resources_user_id", "user_id", unique=True),
        CheckConstraint("coin >= 0", name="ck_resources_coin_non_negative"),
        CheckConstraint("diamond >= 0", name="ck_resources_diamond_non_negative"),
        CheckConstraint("banana >= 0", name="ck_resources_banana_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    coin: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    diamond: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    banana: Mapped[int] = mapped_column(
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

    user: Mapped[User] = relationship(
        "User", back_populates="resources", passive_deletes=True
    )
