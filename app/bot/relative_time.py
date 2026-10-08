"""Telegram's live, locale-aware relative-time entity for MarkdownV2 banners."""

from __future__ import annotations

from datetime import UTC, datetime
from math import ceil


def remaining_time(expires_at: datetime, *, now: datetime | None = None) -> str:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    seconds = max(0, ceil((expires_at - current).total_seconds()))
    if seconds >= 3600:
        amount = f"{ceil(seconds / 3600)} ساعت"
    elif seconds >= 60:
        amount = f"{ceil(seconds / 60)} دقیقه"
    else:
        amount = f"{seconds} ثانیه"
    timestamp = int(expires_at.timestamp())
    return f"||![{amount}](tg://time?unix={timestamp}&format=r)||"
