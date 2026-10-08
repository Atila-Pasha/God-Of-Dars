"""MarkdownV2 banners for chance boxes and arithmetic cards."""

from __future__ import annotations

from datetime import datetime

from app.bot.banners import bold, emoji, escape
from app.bot.relative_time import remaining_time
from app.core.enums import ResourceType


def chance_box_banner(expires_at: datetime) -> str:
    return (
        f"{emoji('5825832256068918886', '📦')} {bold('جعبه شانس')} "
        f"{emoji('5086915529730426905', '⁉️')}\n"
        "حروف داخل تصویر را بخوان و پاسخ درست را انتخاب کن\\.\n"
        "اولین نفری که درست پاسخ دهد، برنده جایزه می‌شود\\!\n\n"
        f"{emoji('5825746176334373354', '😀')} "
        f"زمان باقی‌مانده: {remaining_time(expires_at)}"
    )


def chance_card_banner(expires_at: datetime) -> str:
    return (
        f"{emoji('5267300544094948794', '💳')} {bold('کارت شانس')}\n"
        "کپچا را حل کن تا جایزه‌ات را دریافت کنی\\.\n\n"
        f"{emoji('5825746176334373354', '😀')} "
        f"زمان باقی‌مانده: {remaining_time(expires_at)}"
    )


def chance_box_winner_banner(name: str, amount: int, resource: ResourceType) -> str:
    reward = {
        ResourceType.COIN: ("سکه طلا", emoji("5825699971076202989", "🥇")),
        ResourceType.DIAMOND: ("الماس", emoji("5825753314570018832", "💎")),
        ResourceType.BANANA: ("موز", emoji("5902520589356113908", "🍌")),
    }
    label, icon = reward[resource]
    return (
        f"{emoji('5915892656499597169', '📝')}"
        f"{bold('پاسخ صحیح داده شد')}"
        f"{emoji('5825709849500985213', '✔️')}\n\n"
        f"{emoji('5235470399730361615', '⬅️')} فرمانده « {escape(name)} » "
        "زودتر از همه پاسخ داد\n"
        f" و « {escape(amount)} {label} {icon} » دریافت کرد\\."
    )
