from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ResourceType
from app.db.base import Base
from app.models.resource import RESOURCE_TYPE_ENUM

if TYPE_CHECKING:
    from app.models.user import User


class Reward(Base):
    __tablename__ = "rewards"
    __table_args__ = (
        Index("ix_rewards_user_id", "user_id"),
        Index("ix_rewards_created_at", "created_at"),
        Index(
            "uq_daily_login_reward_per_user_date",
            "user_id",
            "activity_date",
            unique=True,
            postgresql_where=text(
                "source = 'DAILY_LOGIN' AND activity_date IS NOT NULL"
            ),
        ),
        Index(
            "uq_library_reward_per_reference",
            "user_id",
            "source",
            "reference_type",
            "reference_id",
            "resource_type",
            unique=True,
            postgresql_where=text(
                "source IN ('DAILY_QUESTION', 'GROUP_QUESTION') "
                "AND reference_type IS NOT NULL AND reference_id IS NOT NULL"
            ),
            sqlite_where=text(
                "source IN ('DAILY_QUESTION', 'GROUP_QUESTION') "
                "AND reference_type IS NOT NULL AND reference_id IS NOT NULL"
            ),
        ),
        Index(
            "uq_referral_reward_per_reference",
            "user_id",
            "source",
            "reference_type",
            "reference_id",
            unique=True,
            postgresql_where=text(
                "source = 'REFERRAL' AND reference_type IS NOT NULL "
                "AND reference_id IS NOT NULL"
            ),
            sqlite_where=text(
                "source = 'REFERRAL' AND reference_type IS NOT NULL "
                "AND reference_id IS NOT NULL"
            ),
        ),
        CheckConstraint("amount >= 0", name="ck_rewards_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[ResourceType] = mapped_column(
        RESOURCE_TYPE_ENUM, nullable=False
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    activity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship("User", back_populates="rewards")
