"""Telegram's live, locale-aware relative-time entity for MarkdownV2 banners."""

from __future__ import annotations

from datetime import UTC, datetime
from math import ceil


def remaining_time(
    expires_at: datetime,
    *,
    now: datetime | None = None,
    spoiler: bool = True,
    detailed: bool = False,
) -> str:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    seconds = max(0, ceil((expires_at - current).total_seconds()))
    if detailed and seconds >= 86400:
        days, rest = divmod(ceil(seconds / 60), 1440)
        hours, minutes = divmod(rest, 60)
        amount = f"{days} روز"
        if hours:
            amount += f" و {hours} ساعت"
        elif minutes:
            amount += f" و {minutes} دقیقه"
    elif detailed and seconds >= 3600:
        hours, minutes = divmod(ceil(seconds / 60), 60)
        amount = f"{hours} ساعت" + (f" و {minutes} دقیقه" if minutes else "")
    elif seconds >= 3600:
        amount = f"{ceil(seconds / 3600)} ساعت"
    elif seconds >= 60:
        amount = f"{ceil(seconds / 60)} دقیقه"
    else:
        amount = f"{seconds} ثانیه"
    timestamp = int(expires_at.timestamp())
    entity = f"![{amount}](tg://time?unix={timestamp}&format=r)"
    return f"||{entity}||" if spoiler else entity
