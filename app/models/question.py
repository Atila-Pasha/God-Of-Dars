from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import QuestionScope, QuestionStatus
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.answer import Answer
    from app.models.group_question import GroupQuestion


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_questions_scope_status", "scope", "status"),
        Index("ix_questions_published_at", "published_at"),
        Index("ix_questions_expires_at", "expires_at"),
        CheckConstraint(
            "coin_reward >= 0", name="ck_questions_coin_reward_non_negative"
        ),
        CheckConstraint(
            "diamond_reward >= 0", name="ck_questions_diamond_reward_non_negative"
        ),
        CheckConstraint(
            "banana_reward >= 0", name="ck_questions_banana_reward_non_negative"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[QuestionScope] = mapped_column(
        SAEnum(QuestionScope, name="question_scope"),
        nullable=False,
        default=QuestionScope.DAILY,
        server_default=QuestionScope.DAILY.value,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    # The reward belongs to the question, so it is fixed when the question is
    # created and cannot accidentally change between different answers.
    coin_reward: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    diamond_reward: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    banana_reward: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    status: Mapped[QuestionStatus] = mapped_column(
        SAEnum(QuestionStatus, name="question_status"),
        nullable=False,
        default=QuestionStatus.ACTIVE,
        server_default=QuestionStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    answers: Mapped[list[Answer]] = relationship(
        "Answer", back_populates="question", passive_deletes=True
    )
    group_questions: Mapped[list[GroupQuestion]] = relationship(
        "GroupQuestion", back_populates="question", passive_deletes=True
    )
