from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ResourceType
from app.db.base import Base
from app.models.resource import RESOURCE_TYPE_ENUM

if TYPE_CHECKING:
    from app.models.user import User


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_user_id", "user_id"),
        Index("ix_transactions_created_at", "created_at"),
        Index("ix_transactions_user_created_at", "user_id", "created_at"),
        CheckConstraint(
            "balance_before IS NULL OR balance_before >= 0",
            name="ck_transactions_before_non_negative",
        ),
        CheckConstraint(
            "balance_after IS NULL OR balance_after >= 0",
            name="ck_transactions_after_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    resource_type: Mapped[ResourceType] = mapped_column(
        RESOURCE_TYPE_ENUM, nullable=False
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_before: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    balance_after: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship("User", back_populates="transactions")
