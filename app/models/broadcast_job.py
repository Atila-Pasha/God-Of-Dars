"""Durable progress for an admin message sent to all players."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BroadcastJob(Base):
    __tablename__ = "broadcast_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PENDING", server_default="PENDING"
    )
    text: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    photo_data: Mapped[bytes | None] = mapped_column(LargeBinary)
    photo_file_id: Mapped[str | None] = mapped_column(String(512))
    max_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    sent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    failed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
