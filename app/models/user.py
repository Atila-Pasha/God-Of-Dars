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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.answer import Answer
    from app.models.attack import Attack
    from app.models.castle import Castle
    from app.models.mine import Mine
    from app.models.resource import Resource
    from app.models.reward import Reward
    from app.models.transaction import Transaction
    from app.models.user_shield import UserShield
    from app.models.user_teacher import UserTeacher


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_telegram_user_id", "telegram_user_id", unique=True),
        Index("ix_users_username", "username"),
        Index("ix_users_referrer_id", "referrer_id"),
        CheckConstraint("level >= 1", name="ck_users_level_positive"),
        CheckConstraint(
            "referrer_id IS NULL OR referrer_id <> id",
            name="ck_users_cannot_refer_self",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    referrer_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
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

    resources: Mapped[Resource | None] = relationship(
        "Resource",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    castle: Mapped[Castle | None] = relationship(
        "Castle",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    teachers: Mapped[list[UserTeacher]] = relationship(
        "UserTeacher",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    shields: Mapped[list[UserShield]] = relationship(
        "UserShield",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    mine: Mapped[Mine | None] = relationship(
        "Mine",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    attacks_as_attacker: Mapped[list[Attack]] = relationship(
        "Attack",
        foreign_keys="Attack.attacker_id",
        back_populates="attacker",
        passive_deletes=True,
    )
    attacks_as_target: Mapped[list[Attack]] = relationship(
        "Attack",
        foreign_keys="Attack.target_id",
        back_populates="target",
        passive_deletes=True,
    )
    answers: Mapped[list[Answer]] = relationship(
        "Answer", back_populates="user", passive_deletes=True
    )
    rewards: Mapped[list[Reward]] = relationship(
        "Reward", back_populates="user", passive_deletes=True
    )
    transactions: Mapped[list[Transaction]] = relationship(
        "Transaction", back_populates="user", passive_deletes=True
    )
    referrer: Mapped[User | None] = relationship(
        "User", remote_side="User.id", back_populates="referred_users"
    )
    referred_users: Mapped[list[User]] = relationship("User", back_populates="referrer")
