from __future__ import annotations

from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InputRichMessage, Message, ReplyParameters
from aiogram.utils.formatting import Bold, Italic, Pre, Text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import LeaderboardCallback
from app.bot.keyboards.leaderboard import leaderboard_keyboard
from app.bot.keyboards.profile import profile_keyboard
from app.bot.utils.telegram import safe_edit_text
from app.services.leaderboard_service import (
    LeaderboardEntry,
    LeaderboardKind,
    LeaderboardPeriod,
    LeaderboardService,
)
from app.services.school_errors import SchoolUserNotFound
from app.services.user_service import (
    UserInactiveError,
    UserInitializationError,
    UserService,
)

router = Router(name="leaderboard")
leaderboards = LeaderboardService()
users = UserService()

LEADERBOARD_MENU_TEXT = "🏆 برترین‌ها\n\nدسته‌بندی موردنظر را انتخاب کن:"
_GROUP_CATEGORY_PHRASES: dict[str, LeaderboardKind] = {
    "برترین فرمانده": "commander",
    "برترین دانش آموز": "student",
    "برترین دانش آموزش": "student",
    "برترین مبارز": "fighter",
}
GROUP_LEADERBOARD_PHRASES: dict[str, tuple[LeaderboardKind, LeaderboardPeriod]] = {}
_GROUP_PERIOD_SUFFIXES: tuple[tuple[str, LeaderboardPeriod], ...] = (
    ("روزانه", "daily"),
    ("هفتگی", "weekly"),
    ("ماهانه", "monthly"),
)
for _phrase, _kind in _GROUP_CATEGORY_PHRASES.items():
    GROUP_LEADERBOARD_PHRASES[_phrase] = (_kind, "weekly")
    for _suffix, _period in _GROUP_PERIOD_SUFFIXES:
        GROUP_LEADERBOARD_PHRASES[f"{_phrase} {_suffix}"] = (_kind, _period)


def _is_group_leaderboard(message: Message) -> bool:
    return bool(message.text and message.text.strip() in GROUP_LEADERBOARD_PHRASES)


def _number(value: int) -> str:
    return f"{value:,}".translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _account(entry: LeaderboardEntry) -> str:
    value = f"@{entry.username}" if entry.username else entry.name
    value = " ".join(value.replace("|", " ").split())
    return value if len(value) <= 18 else f"{value[:17]}…"


def _rank(entry: LeaderboardEntry) -> str:
    return f"{{}} {_number(entry.rank)}".format(
        {1: "🥇", 2: "🥈", 3: "🥉"}.get(entry.rank, " ")
    ).strip()


def _metrics(kind: LeaderboardKind, entry: LeaderboardEntry) -> tuple[str, str]:
    if kind == "commander":
        return _number(entry.primary_value), _number(entry.secondary_value)
    if kind == "student":
        accuracy = (
            round(entry.primary_value / entry.secondary_value * 100)
            if entry.secondary_value
            else 0
        )
        return _number(entry.primary_value), f"{_number(accuracy)}٪"
    return _number(entry.primary_value), _number(entry.secondary_value)


def _table(kind: LeaderboardKind, entries: tuple[LeaderboardEntry, ...]) -> str:
    primary_header, secondary_header = {
        "commander": ("امتیاز", "سطح"),
        "student": ("صحیح", "دقت"),
        "fighter": ("برد", "آسیب"),
    }[kind]
    account_width = max(
        10,
        min(18, max((len(_account(entry)) for entry in entries), default=10)),
    )
    lines = [
        f"{'رتبه':<7} │ {'اکانت':<{account_width}} │ "
        f"{primary_header:<6} │ {secondary_header}",
        f"{'─' * 7}─┼─{'─' * account_width}─┼─{'─' * 6}─┼─{'─' * 8}",
    ]
    for entry in entries:
        primary, secondary = _metrics(kind, entry)
        lines.append(
            f"{_rank(entry):<7} │ {_account(entry):<{account_width}} │ "
            f"{primary:<6} │ {secondary}"
        )
    return "\n".join(lines)


def _markdown_escape(value: str) -> str:
    for character in ("\\", "|", "*", "_", "[", "]", "<", ">"):
        value = value.replace(character, f"\\{character}")
    return value


def _markdown_table(
    kind: LeaderboardKind, entries: tuple[LeaderboardEntry, ...]
) -> str:
    primary_header, secondary_header = {
        "commander": ("امتیاز", "سطح"),
        "student": ("صحیح", "دقت"),
        "fighter": ("برد", "آسیب"),
    }[kind]
    lines = [
        f"| رتبه | اکانت | {primary_header} | {secondary_header} |",
        "|:---:|:---|---:|---:|",
    ]
    for entry in entries:
        primary, secondary = _metrics(kind, entry)
        lines.append(
            f"| {_rank(entry)} | {_markdown_escape(_account(entry))} | "
            f"{primary} | {secondary} |"
        )
    return "\n".join(lines)


def _period_title(period: LeaderboardPeriod) -> str:
    return {
        "daily": "امروز",
        "weekly": "این هفته",
        "monthly": "این ماه",
    }[period]


def leaderboard_content(
    kind: LeaderboardKind,
    entries: tuple[LeaderboardEntry, ...],
    viewer: LeaderboardEntry | None = None,
    period: LeaderboardPeriod = "weekly",
) -> Text:
    title = {
        "commander": "👑 برترین فرمانده‌ها",
        "student": "📚 برترین دانش‌آموزها",
        "fighter": "⚔️ برترین مبارزها",
    }[kind]
    criterion = {
        "commander": "معیار: موز کسب‌شده در بازه، سپس سطح فرمانده",
        "student": "معیار: پاسخ صحیح، سپس دقت پاسخ‌ها",
        "fighter": "معیار: فرمان حملهٔ موفق، سپس مجموع آسیب",
    }[kind]
    if not entries:
        return Text(
            "🏆 Leaderboard\n",
            Bold(f"{title} — {_period_title(period)}"),
            "\n\nهنوز رکوردی برای این بخش ثبت نشده است.",
        )

    body: list = [
        "🏆 Leaderboard\n",
        Bold(f"{title} — {_period_title(period)}"),
        "\n",
        Italic(criterion),
        "\n\nبا بقیه رقابت کن و خودت را به صدر جدول برسان.\n",
        Bold("آخرین بروزرسانی: "),
        "امروز\n\n",
        Pre(_table(kind, entries)),
    ]
    body.extend(["\n\n", Bold("رتبه شما")])
    if viewer is None:
        body.append("\nهنوز در این جدول رتبه‌ای نداری.")
    else:
        primary, secondary = _metrics(kind, viewer)
        primary_label, secondary_label = {
            "commander": ("امتیاز", "سطح"),
            "student": ("پاسخ صحیح", "دقت"),
            "fighter": ("پیروزی", "آسیب"),
        }[kind]
        body.extend(
            [
                "\n",
                Bold(f"#{_number(viewer.rank)} — {_account(viewer)}"),
                "\n\n",
                Bold(f"{primary} {primary_label}"),
                f" | {secondary} {secondary_label}",
                "\n\nادامه بده و رتبه‌ات را بالاتر ببر 🚀",
            ]
        )
    return Text(*body)


def leaderboard_markdown(
    kind: LeaderboardKind,
    entries: tuple[LeaderboardEntry, ...],
    viewer: LeaderboardEntry | None = None,
    period: LeaderboardPeriod = "weekly",
) -> str:
    title = {
        "commander": "👑 برترین فرمانده‌ها",
        "student": "📚 برترین دانش‌آموزها",
        "fighter": "⚔️ برترین مبارزها",
    }[kind]
    criterion = {
        "commander": "معیار: موز کسب‌شده در بازه، سپس سطح فرمانده",
        "student": "معیار: پاسخ صحیح، سپس دقت پاسخ‌ها",
        "fighter": "معیار: فرمان حملهٔ موفق، سپس مجموع آسیب",
    }[kind]
    heading = f"# 🏆 Leaderboard\n## {title} — {_period_title(period)}"
    if not entries:
        return f"{heading}\n\nهنوز رکوردی برای این بازه ثبت نشده است."

    parts = [
        heading,
        f"*{criterion}*",
        "با بقیه رقابت کن، امتیاز جمع کن و خودت را به صدر جدول برسان.",
        "**آخرین بروزرسانی:** امروز",
        _markdown_table(kind, entries),
        "---\n## رتبه شما",
    ]
    if viewer is None:
        parts.append("هنوز در این جدول رتبه‌ای نداری.")
    else:
        primary, secondary = _metrics(kind, viewer)
        primary_label, secondary_label = {
            "commander": ("امتیاز", "سطح"),
            "student": ("پاسخ صحیح", "دقت"),
            "fighter": ("پیروزی", "آسیب"),
        }[kind]
        parts.extend(
            [
                f"**#{_number(viewer.rank)} — {_markdown_escape(_account(viewer))}**",
                f"**{primary} {primary_label}** | {secondary} {secondary_label}",
                "ادامه بده و رتبه‌ات را بالاتر ببر 🚀",
            ]
        )
    return "\n\n".join(parts)


def leaderboard_text(
    kind: LeaderboardKind,
    entries: tuple[LeaderboardEntry, ...],
    viewer: LeaderboardEntry | None = None,
    period: LeaderboardPeriod = "weekly",
) -> str:
    """Return the rendered text for tests and non-Telegram consumers."""
    return leaderboard_content(kind, entries, viewer, period).render()[0]


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
    period: LeaderboardPeriod,
    with_keyboard: bool,
) -> None:
    entries = await leaderboards.top(session, kind, period=period)
    viewer = None
    if target.from_user is not None:
        try:
            user = await users.get_active_by_telegram_user_id(
                session, target.from_user.id
            )
            viewer = await leaderboards.position(
                session, kind, user_id=user.id, period=period
            )
        except (SchoolUserNotFound, UserInactiveError, UserInitializationError):
            pass
    rich_message = InputRichMessage(
        markdown=leaderboard_markdown(kind, entries, viewer, period),
        is_rtl=True,
    )
    markup = (
        leaderboard_keyboard(active_kind=kind, active_period=period)
        if with_keyboard
        else None
    )
    if isinstance(target, CallbackQuery):
        if not isinstance(target.message, Message):
            return
        editable_message = target.message
        try:
            await editable_message.edit_text(
                text=None,
                rich_message=rich_message,
                reply_markup=markup,
            )
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
    else:
        bot = target.bot
        if bot is not None:
            try:
                reply = (
                    ReplyParameters(message_id=target.message_id)
                    if target.chat.type in {"group", "supergroup"}
                    else None
                )
                await bot.send_rich_message(
                    chat_id=target.chat.id,
                    rich_message=rich_message,
                    reply_markup=markup,
                    reply_parameters=reply,
                )
                return
            except TelegramBadRequest:
                pass

    # Compatibility fallback for an older self-hosted Bot API server. The
    # official API supports Rich Markdown, but a stale local server may not.
    content = leaderboard_content(kind, entries, viewer, period)
    rendered = content.as_kwargs()
    text = rendered.pop("text")
    if isinstance(target, CallbackQuery):
        await safe_edit_text(editable_message, text, reply_markup=markup, **rendered)
    else:
        await target.answer(text, reply_markup=markup, **rendered)


@router.message(Command("leaderbord", "leaderboard"), F.chat.type == "private")
async def leaderboard_command_handler(message: Message) -> None:
    await _show_menu(message)


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    _is_group_leaderboard,
)
async def group_leaderboard_handler(message: Message, session: AsyncSession) -> None:
    if message.text is None:
        return
    phrase = message.text.strip()
    kind, period = GROUP_LEADERBOARD_PHRASES[phrase]
    try:
        await _show_board(
            message,
            session,
            kind,
            period=period,
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
                period=callback_data.period,
                with_keyboard=True,
            )
    except SQLAlchemyError:
        await callback.answer("اطلاعات برترین‌ها فعلاً در دسترس نیست.", show_alert=True)
        return
    with suppress(TelegramAPIError):
        await callback.answer()
