from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import QuestionStatus
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.answer import Answer
    from app.models.group import Group
    from app.models.question import Question


class GroupQuestion(Base):
    """A publication of a question to one Telegram group."""

    __tablename__ = "group_questions"
    __table_args__ = (
        Index(
            "uq_group_question_publication",
            "question_id",
            "group_id",
            unique=True,
        ),
        Index("ix_group_questions_group_status", "group_id", "status"),
        Index("ix_group_questions_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False
    )
    group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("groups.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[QuestionStatus] = mapped_column(
        SAEnum(QuestionStatus, name="question_status"),
        nullable=False,
        default=QuestionStatus.ACTIVE,
        server_default=QuestionStatus.ACTIVE.value,
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    question: Mapped[Question] = relationship(
        "Question", back_populates="group_questions"
    )
    group: Mapped[Group] = relationship("Group", back_populates="group_questions")
    answers: Mapped[list[Answer]] = relationship(
        "Answer", back_populates="group_question", passive_deletes=True
    )
