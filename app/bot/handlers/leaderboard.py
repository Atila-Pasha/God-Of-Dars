from __future__ import annotations

from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import LeaderboardCallback
from app.bot.keyboards.leaderboard import leaderboard_keyboard
from app.bot.keyboards.profile import profile_keyboard
from app.bot.utils.telegram import safe_edit_text
from app.services.leaderboard_service import (
    LeaderboardEntry,
    LeaderboardKind,
    LeaderboardService,
)

router = Router(name="leaderboard")
leaderboards = LeaderboardService()

LEADERBOARD_MENU_TEXT = "🏆 برترین‌ها\n\nدسته‌بندی موردنظر را انتخاب کن:"
GROUP_LEADERBOARD_PHRASES: dict[str, LeaderboardKind] = {
    "برترین فرمانده": "commander",
    "برترین دانش آموز": "student",
    # Keep the spelling from the public command contract as an alias.
    "برترین دانش آموزش": "student",
    "برترین مبارز": "fighter",
}


def _number(value: int) -> str:
    return f"{value:,}".translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _identity(entry: LeaderboardEntry) -> str:
    username = f" (@{entry.username})" if entry.username else ""
    return f"{entry.name}{username}"


def _rank_icon(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"{_number(rank)}.")


def _entry_text(kind: LeaderboardKind, entry: LeaderboardEntry) -> str:
    identity = _identity(entry)
    if kind == "commander":
        stats = (
            f"سطح {_number(entry.primary_value)} | XP: {_number(entry.secondary_value)}"
        )
    elif kind == "student":
        accuracy = (
            round(entry.primary_value / entry.secondary_value * 100)
            if entry.secondary_value
            else 0
        )
        stats = f"{_number(entry.primary_value)} پاسخ صحیح | دقت {_number(accuracy)}٪"
    else:
        stats = (
            f"{_number(entry.primary_value)} پیروزی | "
            f"{_number(entry.secondary_value)} آسیب"
        )
    return f"{_rank_icon(entry.rank)} {identity}\n   {stats}"


def leaderboard_text(
    kind: LeaderboardKind, entries: tuple[LeaderboardEntry, ...]
) -> str:
    title = {
        "commander": "👑 برترین فرمانده‌ها",
        "student": "📚 برترین دانش‌آموزها",
        "fighter": "⚔️ برترین مبارزها",
    }[kind]
    criterion = {
        "commander": "معیار: سطح فرمانده، سپس XP فعلی",
        "student": "معیار: پاسخ صحیح، سپس دقت پاسخ‌ها",
        "fighter": "معیار: فرمان حملهٔ موفق، سپس مجموع آسیب",
    }[kind]
    if not entries:
        return f"{title}\n\nهنوز رکوردی برای این بخش ثبت نشده است."
    rows = "\n\n".join(_entry_text(kind, entry) for entry in entries)
    return f"{title}\n{criterion}\n\n{rows}"


async def _show_menu(target: Message | CallbackQuery) -> None:
    if isinstance(target, CallbackQuery):
        if target.message is None:
            return
        await safe_edit_text(
            target.message,
            LEADERBOARD_MENU_TEXT,
            reply_markup=leaderboard_keyboard(),
        )
    else:
        await target.answer(
            LEADERBOARD_MENU_TEXT,
            reply_markup=leaderboard_keyboard(),
        )


async def _show_board(
    target: Message | CallbackQuery,
    session: AsyncSession,
    kind: LeaderboardKind,
    *,
    with_keyboard: bool,
) -> None:
    entries = await leaderboards.top(session, kind)
    text = leaderboard_text(kind, entries)
    markup = leaderboard_keyboard() if with_keyboard else None
    if isinstance(target, CallbackQuery):
        if target.message is None:
            return
        await safe_edit_text(target.message, text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(Command("leaderbord", "leaderboard"), F.chat.type == "private")
async def leaderboard_command_handler(message: Message) -> None:
    await _show_menu(message)


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.regexp(
        r"^\s*(?:برترین فرمانده|برترین دانش آموز|برترین دانش آموزش|برترین مبارز)\s*$"
    ),
)
async def group_leaderboard_handler(message: Message, session: AsyncSession) -> None:
    if message.text is None:
        return
    phrase = message.text.strip()
    try:
        await _show_board(
            message,
            session,
            GROUP_LEADERBOARD_PHRASES[phrase],
            with_keyboard=False,
        )
    except SQLAlchemyError:
        await message.answer("اطلاعات برترین‌ها فعلاً در دسترس نیست.")


@router.callback_query(LeaderboardCallback.filter())
async def leaderboard_callback_handler(
    callback: CallbackQuery,
    callback_data: LeaderboardCallback,
    session: AsyncSession,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    if callback.message.chat.type in {"group", "supergroup"}:
        await callback.answer(
            "دکمه‌های برترین‌ها فقط در گفت‌وگوی خصوصی فعال‌اند.",
            show_alert=True,
        )
        return

    try:
        if callback_data.action == "back":
            owner_id = callback.from_user.id if callback.from_user else 0
            await safe_edit_text(
                callback.message,
                "🧙 پروفایل فرمانده\n\nیکی از موارد زیر را انتخاب کن:",
                reply_markup=profile_keyboard(owner_id=owner_id),
            )
        elif callback_data.action == "menu":
            await _show_menu(callback)
        else:
            await _show_board(
                callback,
                session,
                callback_data.action,
                with_keyboard=True,
            )
    except SQLAlchemyError:
        await callback.answer("اطلاعات برترین‌ها فعلاً در دسترس نیست.", show_alert=True)
        return
    with suppress(TelegramAPIError):
        await callback.answer()
