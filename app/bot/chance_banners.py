"""MarkdownV2 banners for chance boxes and arithmetic cards."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.bot.banners import bold, emoji, escape


def chance_box_banner(minutes: int) -> str:
    return (
        f"{emoji('5825832256068918886', '📦')} {bold('جعبه شانس')} "
        f"{emoji('5086915529730426905', '⁉️')}\n"
        "اولین نفری که جعبه را باز کند، برنده جایزه می‌شود\\!\n\n"
        f"{emoji('5825746176334373354', '😀')} "
        f"اعتبار ||{escape(minutes)} دقیقه||"
    )


def chance_card_banner(expires_at: datetime) -> str:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    deadline = expires_at.astimezone(ZoneInfo("Asia/Tehran")).strftime("%H:%M")
    return (
        f"{emoji('5267300544094948794', '💳')} {bold('کارت شانس')}\n"
        "کپچا را حل کن تا جایزه‌ات را دریافت کنی\\.\n\n"
        f"{emoji('5825746176334373354', '😀')} "
        f"مهلت تا ||{deadline}||"
    )
