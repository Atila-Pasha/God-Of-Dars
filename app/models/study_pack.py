from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StudyPack(Base):
    __tablename__ = "study_packs"
    __table_args__ = (
        CheckConstraint(
            "duration_minutes > 0", name="ck_study_packs_duration_positive"
        ),
        CheckConstraint(
            "reward_amount >= 0", name="ck_study_packs_reward_non_negative"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    reward_resource: Mapped[str] = mapped_column(String(16), nullable=False)
    reward_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
