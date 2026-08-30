from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import TeacherStatus
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.attack import Attack
    from app.models.recovery import Recovery
    from app.models.teacher import Teacher
    from app.models.user import User


class UserTeacher(Base):
    __tablename__ = "user_teachers"
    __table_args__ = (
        Index("ix_user_teachers_user_id", "user_id"),
        Index("ix_user_teachers_teacher_id", "teacher_id"),
        Index("uq_user_teachers_user_teacher", "user_id", "teacher_id", unique=True),
        CheckConstraint("level >= 1", name="ck_user_teachers_level_positive"),
        CheckConstraint(
            "current_hp >= 0", name="ck_user_teachers_current_hp_non_negative"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    teacher_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teachers.id", ondelete="RESTRICT"), nullable=False
    )
    level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    current_hp: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TeacherStatus] = mapped_column(
        SAEnum(TeacherStatus, name="teacher_status"),
        nullable=False,
        default=TeacherStatus.ACTIVE,
        server_default=TeacherStatus.ACTIVE.value,
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

    user: Mapped[User] = relationship("User", back_populates="teachers")
    teacher: Mapped[Teacher] = relationship("Teacher", back_populates="owned_by_users")
    attacks: Mapped[list[Attack]] = relationship(
        "Attack", back_populates="teacher", passive_deletes=True
    )
    recoveries: Mapped[list[Recovery]] = relationship(
        "Recovery", back_populates="user_teacher", passive_deletes=True
    )
