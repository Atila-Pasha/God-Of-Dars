from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user_teacher import UserTeacher


class Recovery(Base):
    __tablename__ = "recoveries"
    __table_args__ = (
        Index("ix_recoveries_user_teacher_id", "user_teacher_id"),
        Index("ix_recoveries_recovery_end_at", "recovery_end_at"),
        Index(
            "uq_active_recovery_per_teacher",
            "user_teacher_id",
            unique=True,
            postgresql_where=text("completed_at IS NULL"),
        ),
        CheckConstraint(
            "recovery_end_at > recovery_started_at",
            name="ck_recoveries_end_after_start",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_teacher_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_teachers.id", ondelete="SET NULL"), nullable=True
    )
    recovery_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    recovery_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
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

    user_teacher: Mapped[UserTeacher | None] = relationship(
        "UserTeacher", back_populates="recoveries", passive_deletes=True
    )
