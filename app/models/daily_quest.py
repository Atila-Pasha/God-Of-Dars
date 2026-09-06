from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


QUEST_TYPES = (
    "DAILY_LOGIN",
    "ANSWER_DAILY_QUESTION",
    "CORRECT_ANSWERS",
    "COMPLETE_BATTLES",
    "WIN_BATTLES",
    "COLLECT_MINE",
    "JOIN_CHANNEL",
)


class DailyQuest(Base):
    __tablename__ = "daily_quests"
    __table_args__ = (
        Index("ix_daily_quests_date_active", "activity_date", "is_active"),
        CheckConstraint("target > 0", name="ck_daily_quests_target_positive"),
        CheckConstraint(
            "quest_type IN ('DAILY_LOGIN','ANSWER_DAILY_QUESTION','CORRECT_ANSWERS','COMPLETE_BATTLES','WIN_BATTLES','COLLECT_MINE','JOIN_CHANNEL')",
            name="ck_daily_quests_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    activity_date: Mapped[date] = mapped_column(Date, nullable=False)
    quest_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    target: Mapped[int] = mapped_column(Integer, nullable=False)
    rewards: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    quest_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
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
    progresses: Mapped[list[DailyQuestProgress]] = relationship(
        "DailyQuestProgress", back_populates="quest", cascade="all, delete-orphan"
    )


class DailyQuestProgress(Base):
    __tablename__ = "daily_quest_progress"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "quest_id", name="uq_daily_quest_progress_user_quest"
        ),
        Index("ix_daily_quest_progress_user_date", "user_id", "activity_date"),
        CheckConstraint("progress >= 0", name="ck_daily_quest_progress_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    quest_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("daily_quests.id", ondelete="CASCADE"), nullable=False
    )
    activity_date: Mapped[date] = mapped_column(Date, nullable=False)
    progress: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    quest: Mapped[DailyQuest] = relationship("DailyQuest", back_populates="progresses")
    user: Mapped[User] = relationship("User")


class DailyQuestEvent(Base):
    __tablename__ = "daily_quest_events"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "activity_date",
            "event_key",
            name="uq_daily_quest_event_idempotency",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    activity_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
