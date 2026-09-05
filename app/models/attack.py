from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AttackStatus
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.user_teacher import UserTeacher


class Attack(Base):
    __tablename__ = "attacks"
    __table_args__ = (
        Index("ix_attacks_attacker_id", "attacker_id"),
        Index("ix_attacks_target_id", "target_id"),
        Index("ix_attacks_teacher_id", "teacher_id"),
        Index("ix_attacks_status", "status"),
        Index("ix_attacks_resolve_at", "resolve_at"),
            Index("ix_attacks_attack_command_id", "attack_command_id"),
        Index(
            "uq_pending_attack_per_teacher",
            "attacker_id",
            "target_id",
            "teacher_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        CheckConstraint(
            "teacher_damage_snapshot >= 0",
            name="ck_attacks_teacher_damage_non_negative",
        ),
        CheckConstraint(
            "target_castle_strength_snapshot >= 0",
            name="ck_attacks_castle_strength_non_negative",
        ),
        CheckConstraint(
            "target_defense_power_snapshot >= 0",
            name="ck_attacks_defense_power_non_negative",
        ),
        CheckConstraint(
            "result_damage >= 0", name="ck_attacks_result_damage_non_negative"
        ),
        CheckConstraint("loot_coin >= 0", name="ck_attacks_loot_coin_non_negative"),
        CheckConstraint(
            "loot_diamond >= 0", name="ck_attacks_loot_diamond_non_negative"
        ),
        CheckConstraint("loot_banana >= 0", name="ck_attacks_loot_banana_non_negative"),
        CheckConstraint("attacker_id <> target_id", name="ck_attacks_different_users"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    attacker_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    target_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    teacher_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_teachers.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[AttackStatus] = mapped_column(
        SAEnum(AttackStatus, name="attack_status"),
        nullable=False,
        default=AttackStatus.PENDING,
        server_default=AttackStatus.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolve_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attack_command_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    attack_xp_awarded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    teacher_damage_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    target_castle_strength_snapshot: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )
    target_defense_power_snapshot: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )
    result_damage: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    loot_coin: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    loot_diamond: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    loot_banana: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_successful: Mapped[bool | None] = mapped_column(nullable=True)

    attacker: Mapped[User] = relationship(
        "User",
        foreign_keys=[attacker_id],
        back_populates="attacks_as_attacker",
        passive_deletes=True,
    )
    target: Mapped[User] = relationship(
        "User",
        foreign_keys=[target_id],
        back_populates="attacks_as_target",
        passive_deletes=True,
    )
    teacher: Mapped[UserTeacher | None] = relationship(
        "UserTeacher", back_populates="attacks", passive_deletes=True
    )
