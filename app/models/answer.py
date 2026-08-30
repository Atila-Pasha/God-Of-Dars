from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.group import Group
    from app.models.question import Question
    from app.models.user import User


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        Index("ix_answers_question_id", "question_id"),
        Index("ix_answers_group_id", "group_id"),
        Index("ix_answers_user_id", "user_id"),
        Index(
            "uq_valid_group_question_answer",
            "question_id",
            "group_id",
            unique=True,
            postgresql_where=text("group_id IS NOT NULL AND is_valid = true"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False
    )
    group_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("groups.id", ondelete="RESTRICT"), nullable=True
    )
    answer_content: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_valid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship("User", back_populates="answers")
    question: Mapped[Question] = relationship("Question", back_populates="answers")
    group: Mapped[Group | None] = relationship("Group", back_populates="answers")
