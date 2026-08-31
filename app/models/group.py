from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.answer import Answer
    from app.models.group_question import GroupQuestion


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        Index("ix_groups_telegram_chat_id", "telegram_chat_id", unique=True),
        Index("ix_groups_username", "username"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
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

    answers: Mapped[list[Answer]] = relationship(
        "Answer", back_populates="group", passive_deletes=True
    )
    group_questions: Mapped[list[GroupQuestion]] = relationship(
        "GroupQuestion", back_populates="group", passive_deletes=True
    )
