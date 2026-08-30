from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BotSettings(Base):
    __tablename__ = "bot_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_bot_settings_singleton"),)

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, default=1, server_default="1", autoincrement=False
    )
    required_channel_telegram_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    required_channel_username: Mapped[str | None] = mapped_column(
        String(255), nullable=True
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
