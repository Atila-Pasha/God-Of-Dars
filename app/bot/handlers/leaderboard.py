from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime
from time import monotonic
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InputRichMessage, Message, ReplyParameters
from aiogram.utils.formatting import Bold, Italic, Pre, Text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.banners import emoji
from app.bot.callbacks import GlobalRankCallback, LeaderboardCallback
from app.bot.keyboards.leaderboard import global_rank_keyboard, leaderboard_keyboard
from app.bot.keyboards.profile import profile_keyboard
from app.bot.leaderboard_widget import (
    global_rank_widget_html,
    leaderboard_widget_html,
    send_leaderboard_widget,
)
from app.bot.utils.telegram import safe_edit_text
from app.core.config import settings
from app.services.leaderboard_service import (
    FighterPage,
    LeaderboardEntry,
    LeaderboardKind,
    LeaderboardPeriod,
    LeaderboardService,
)
from app.services.rank_service import TIERS, tier_for
from app.services.school_errors import SchoolUserNotFound
from app.services.user_service import (
    UserInactiveError,
    UserInitializationError,
    UserService,
)

router = Router(name="leaderboard")
leaderboards = LeaderboardService(
    cache_ttl_seconds=settings.LEADERBOARD_CACHE_TTL_SECONDS
)
users = UserService()
_viewer_ids: dict[int, tuple[float, int | None]] = {}
_viewer_ids_lock = asyncio.Lock()


async def _viewer_user_id(session: AsyncSession, telegram_user_id: int) -> int | None:
    cached = _viewer_ids.get(telegram_user_id)
    if cached is not None and cached[0] > monotonic():
        return cached[1]
    async with _viewer_ids_lock:
        cached = _viewer_ids.get(telegram_user_id)
        if cached is not None and cached[0] > monotonic():
            return cached[1]
        try:
            user = await users.get_active_by_telegram_user_id(session, telegram_user_id)
        except (SchoolUserNotFound, UserInactiveError, UserInitializationError):
            _viewer_ids[telegram_user_id] = (monotonic() + 60, None)
            if len(_viewer_ids) > 20_000:
                _viewer_ids.pop(next(iter(_viewer_ids)))
            return None
        _viewer_ids[telegram_user_id] = (
            monotonic() + settings.LEADERBOARD_CACHE_TTL_SECONDS,
            user.id,
        )
        if len(_viewer_ids) > 20_000:
            _viewer_ids.pop(next(iter(_viewer_ids)))
        return user.id


def _updated_label(updated_at: datetime | None) -> str:
    if updated_at is None:
        return ""
    local = updated_at.astimezone(ZoneInfo(settings.LEADERBOARD_TIMEZONE))
    return f"آخرین به‌روزرسانی: {local:%Y/%m/%d، %H:%M}"


LEADERBOARD_MENU_TEXT = (
    "🏆 تالار قهرمانان\n\nاسم چه کسی باید بالای جدول بدرخشه؟ دسته‌بندی رو انتخاب کن 👇"
)
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
    GROUP_LEADERBOARD_PHRASES[_phrase] = (
        _kind,
        "monthly" if _kind == "fighter" else "weekly",
    )
    for _suffix, _period in _GROUP_PERIOD_SUFFIXES:
        if _kind == "fighter" and _period != "monthly":
            continue
        GROUP_LEADERBOARD_PHRASES[f"{_phrase} {_suffix}"] = (
            _kind,
            "monthly" if _kind == "fighter" else _period,
        )


def _is_group_leaderboard(message: Message) -> bool:
    return bool(message.text and message.text.strip() in GROUP_LEADERBOARD_PHRASES)


def _number(value: int) -> str:
    return f"{value:,}"


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
        "fighter": ("جام", "برد"),
    }[kind]
    account_width = max(
        10,
        min(18, max((len(_account(entry)) for entry in entries), default=10)),
    )
    lines = [
        f"{'رتبه':<7} │ {'اکانت':<{account_width}} │ "
        f"{primary_header:<6} │ {secondary_header}",
    ]
    for entry in entries:
        primary, secondary = _metrics(kind, entry)
        lines.append(
            f"{_rank(entry):<7} │ {_account(entry):<{account_width}} │ "
            f"{primary:<6} │ {secondary}"
        )
    return "\n".join(lines)


def _markdown_escape(value: str) -> str:
    for character in ("\\", "|", "*", "_", "[", "]", "<", ">", "`", "!"):
        value = value.replace(character, f"\\{character}")
    return value


def _markdown_table(
    kind: LeaderboardKind, entries: tuple[LeaderboardEntry, ...]
) -> str:
    primary_header, secondary_header = {
        "commander": ("امتیاز", "سطح"),
        "student": ("صحیح", "دقت"),
        "fighter": ("جام", "برد"),
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
    updated_at: datetime | None = None,
) -> Text:
    if kind == "fighter":
        period = "monthly"
    title = {
        "commander": "👑 برترین فرمانده‌ها",
        "student": "📚 برترین دانش‌آموزها",
        "fighter": "⚔️ برترین مبارزها",
    }[kind]
    criterion = {
        "commander": "معیار: موز کسب‌شده در بازه، سپس سطح فرمانده",
        "student": "معیار: پاسخ صحیح، سپس دقت پاسخ‌ها",
        "fighter": "معیار: جام فصل رنک، سپس تعداد برد",
    }[kind]
    if not entries:
        return Text(
            "🏆 Leaderboard\n",
            Bold(f"{title} — {_period_title(period)}"),
            f"\n{_updated_label(updated_at)}\n\nهنوز رکوردی برای این بخش ثبت نشده است.",
        )

    body: list = [
        "🏆 Leaderboard\n",
        Bold(f"{title} — {_period_title(period)}"),
        "\n",
        Italic(criterion),
        "\n\nبا بقیه رقابت کن و خودت را به صدر جدول برسان.\n",
        _updated_label(updated_at) + "\n\n",
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
            "fighter": ("جام", "برد"),
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
    updated_at: datetime | None = None,
) -> str:
    if kind == "fighter":
        period = "monthly"
    title = {
        "commander": "👑 برترین فرمانده‌ها",
        "student": "📚 برترین دانش‌آموزها",
        "fighter": "⚔️ برترین مبارزها",
    }[kind]
    criterion = {
        "commander": "معیار: موز کسب‌شده در بازه، سپس سطح فرمانده",
        "student": "معیار: پاسخ صحیح، سپس دقت پاسخ‌ها",
        "fighter": "معیار: جام فصل رنک، سپس تعداد برد",
    }[kind]
    heading = f"# 🏆 Leaderboard\n## {title} — {_period_title(period)}"
    if not entries:
        return f"{heading}\n\n{_updated_label(updated_at)}\n\nهنوز رکوردی برای این بازه ثبت نشده است."

    parts = [
        heading,
        f"*{criterion}*",
        "با بقیه رقابت کن، امتیاز جمع کن و خودت را به صدر جدول برسان.",
        f"**{_updated_label(updated_at)}**",
        _markdown_table(kind, entries),
        "## رتبه شما",
    ]
    if viewer is None:
        parts.append("هنوز در این جدول رتبه‌ای نداری.")
    else:
        primary, secondary = _metrics(kind, viewer)
        primary_label, secondary_label = {
            "commander": ("امتیاز", "سطح"),
            "student": ("پاسخ صحیح", "دقت"),
            "fighter": ("جام", "برد"),
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


def _global_rank_table(entries: tuple[LeaderboardEntry, ...]) -> str:
    account_width = max(
        10,
        min(18, max((len(_account(entry)) for entry in entries), default=10)),
    )
    lines = [f"{'#':<4} │ {'مبارز':<{account_width}} │ {'جام':<6} │ رنک"]
    for entry in entries:
        tier = tier_for(entry.primary_value)
        lines.append(
            f"{entry.rank:<4} │ {_account(entry):<{account_width}} │ "
            f"{_number(entry.primary_value):<6} │ {tier.icon} {tier.name}"
        )
    return "\n".join(lines)


def _global_rank_markdown_table(entries: tuple[LeaderboardEntry, ...]) -> str:
    lines = [
        "| # | مبارز | جام | رنک |",
        "|:---:|:---|---:|:---|",
    ]
    for entry in entries:
        tier = tier_for(entry.primary_value)
        lines.append(
            f"| {_rank(entry)} | {_markdown_escape(_account(entry))} | "
            f"{_number(entry.primary_value)} | "
            f"{emoji(tier.emoji_id, tier.icon)} {tier.name} |"
        )
    return "\n".join(lines)


def _global_rank_spotlight(page: FighterPage) -> str | None:
    if page.page != 1 or not page.entries:
        return None
    champion = page.entries[0]
    return (
        f"👑 صدرنشین فصل: {_account(champion)} · {_number(champion.primary_value)} جام"
    )


def _global_rank_progress(viewer: LeaderboardEntry | None) -> str:
    if viewer is None:
        return "هنوز وارد رنک این فصل نشده‌ای. با /rank شروع کن."
    tier = tier_for(viewer.primary_value)
    next_tier = next(
        (item for item in TIERS if item.minimum > viewer.primary_value), None
    )
    progress = (
        f"تا {next_tier.name}: {_number(next_tier.minimum - viewer.primary_value)} جام"
        if next_tier is not None
        else "به بالاترین رنک رسیده‌ای؛ حالا برای صدر جدول بجنگ!"
    )
    return (
        f"#{viewer.rank} · {tier.icon} {tier.name} · "
        f"{_number(viewer.primary_value)} جام\n🚀 {progress}"
    )


def global_rank_content(page: FighterPage, viewer: LeaderboardEntry | None) -> Text:
    body: list = [
        "🏆 ",
        Bold("تالار مبارزان سراسری"),
        "\n⚔️ نبرد برای تاج رنک · فصل ماهانه",
        f"\n👥 {_number(page.total)} مبارز  ·  صفحه {page.page}/{page.pages}",
        f"\n{_updated_label(page.updated_at)}",
        "\n\n",
    ]
    spotlight = _global_rank_spotlight(page)
    if spotlight is not None:
        body.extend([Bold(spotlight), "\n\n"])
    if page.entries:
        body.append(Pre(_global_rank_table(page.entries)))
    else:
        body.append("هنوز مبارزی در رنک این فصل ثبت نشده است.")
    body.extend(["\n\n", Bold("جایگاه تو")])
    body.extend(["\n", _global_rank_progress(viewer)])
    body.append("\n\nجام بیشتر، جایگاه بالاتر؛ در تساوی جام، برد بیشتر جلوتر است.")
    return Text(*body)


def global_rank_markdown(page: FighterPage, viewer: LeaderboardEntry | None) -> str:
    heading = (
        f"# {emoji('5823430604846276719', '🏆')} تالار مبارزان سراسری\n"
        f"## {emoji('5825697157872623308', '⚔️')} "
        "نبرد برای تاج رنک · فصل ماهانه"
    )
    summary = f"**👥 {_number(page.total)} مبارز  ·  صفحه {page.page}/{page.pages}**\n{_updated_label(page.updated_at)}"
    table = (
        _global_rank_markdown_table(page.entries)
        if page.entries
        else "هنوز مبارزی در رنک این فصل ثبت نشده است."
    )
    if viewer is None:
        position = _global_rank_progress(None)
    else:
        tier = tier_for(viewer.primary_value)
        next_tier = next(
            (item for item in TIERS if item.minimum > viewer.primary_value), None
        )
        progress = (
            f"تا {next_tier.name}: {_number(next_tier.minimum - viewer.primary_value)} جام"
            if next_tier is not None
            else "به بالاترین رنک رسیده‌ای؛ حالا برای صدر جدول بجنگ!"
        )
        position = (
            f"**#{viewer.rank} · {emoji(tier.emoji_id, tier.icon)} "
            f"{tier.name} · {_number(viewer.primary_value)} جام**\n"
            f"🚀 {_markdown_escape(progress)}"
        )
    parts = [heading, summary]
    spotlight = _global_rank_spotlight(page)
    if spotlight is not None:
        parts.append("**" + _markdown_escape(spotlight) + "**")
    parts.extend(
        [
            table,
            "## 🎖️ جایگاه تو\n" + position,
            "*جام بیشتر، جایگاه بالاتر؛ در تساوی جام، برد بیشتر جلوتر است.*",
        ]
    )
    return "\n\n".join(parts)


async def _show_global_rank(
    target: Message | CallbackQuery, session: AsyncSession, *, page: int = 1
) -> None:
    result = await leaderboards.fighter_page(session, page)
    viewer = None
    if target.from_user is not None:
        user_id = await _viewer_user_id(session, target.from_user.id)
        if user_id is not None:
            viewer = await leaderboards.position(
                session, "fighter", user_id=user_id, period="monthly"
            )
    rich_message = InputRichMessage(
        markdown=global_rank_markdown(result, viewer), is_rtl=True
    )
    if isinstance(target, CallbackQuery):
        if not isinstance(target.message, Message):
            return
        chat = target.message.chat
    else:
        chat = target.chat
    markup = global_rank_keyboard(
        result.page, result.pages, private=chat.type == "private"
    )
    bot = target.bot
    if bot is not None:
        reply = (
            ReplyParameters(message_id=target.message_id)
            if isinstance(target, Message) and chat.type in {"group", "supergroup"}
            else None
        )
        sent = await send_leaderboard_widget(
            bot,
            chat.id,
            global_rank_widget_html(result, viewer),
            caption=f"🏆 تالار مبارزان سراسری · صفحه {result.page}/{result.pages}\n{_updated_label(result.updated_at)}",
            reply_markup=markup,
            reply_parameters=reply,
        )
        if sent:
            if isinstance(target, CallbackQuery) and isinstance(
                target.message, Message
            ):
                with suppress(TelegramAPIError):
                    await target.message.delete()
            return
    if isinstance(target, CallbackQuery):
        if not isinstance(target.message, Message):
            return
        editable_message = target.message
        if editable_message.text is None and editable_message.rich_message is None:
            content = global_rank_content(result, viewer)
            rendered = content.as_kwargs()
            text = rendered.pop("text")
            await editable_message.answer(text, reply_markup=markup, **rendered)
            with suppress(TelegramAPIError):
                await editable_message.delete()
            return
        try:
            await editable_message.edit_text(
                text=None, rich_message=rich_message, reply_markup=markup
            )
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
        content = global_rank_content(result, viewer)
        rendered = content.as_kwargs()
        text = rendered.pop("text")
        await safe_edit_text(editable_message, text, reply_markup=markup, **rendered)
        return
    if bot is not None:
        try:
            reply = (
                ReplyParameters(message_id=target.message_id)
                if chat.type in {"group", "supergroup"}
                else None
            )
            await bot.send_rich_message(
                chat_id=chat.id,
                rich_message=rich_message,
                reply_markup=markup,
                reply_parameters=reply,
            )
            return
        except TelegramBadRequest:
            pass
    content = global_rank_content(result, viewer)
    rendered = content.as_kwargs()
    text = rendered.pop("text")
    await target.answer(text, reply_markup=markup, **rendered)


async def _show_menu(target: Message | CallbackQuery) -> None:
    if isinstance(target, CallbackQuery):
        if target.message is None:
            return
        if isinstance(target.message, Message) and target.message.text is None:
            await target.message.answer(
                LEADERBOARD_MENU_TEXT,
                reply_markup=leaderboard_keyboard(),
            )
            with suppress(TelegramAPIError):
                await target.message.delete()
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
    if kind == "fighter":
        period = "monthly"
    snapshot = await leaderboards.top_snapshot(session, kind, period=period)
    entries = snapshot.entries
    viewer = None
    if target.from_user is not None:
        user_id = await _viewer_user_id(session, target.from_user.id)
        if user_id is not None:
            viewer = await leaderboards.position(
                session, kind, user_id=user_id, period=period
            )
    rich_message = InputRichMessage(
        markdown=leaderboard_markdown(
            kind, entries, viewer, period, snapshot.updated_at
        ),
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
        chat_id = target.message.chat.id
    else:
        chat_id = target.chat.id
    bot = target.bot
    if bot is not None:
        reply = (
            ReplyParameters(message_id=target.message_id)
            if isinstance(target, Message)
            and target.chat.type in {"group", "supergroup"}
            else None
        )
        sent = await send_leaderboard_widget(
            bot,
            chat_id,
            leaderboard_widget_html(kind, entries, viewer, period, snapshot.updated_at),
            caption=f"🏆 برترین‌های {_period_title(period)}\n{_updated_label(snapshot.updated_at)}",
            reply_markup=markup,
            reply_parameters=reply,
        )
        if sent:
            if isinstance(target, CallbackQuery) and isinstance(
                target.message, Message
            ):
                with suppress(TelegramAPIError):
                    await target.message.delete()
            return
    if isinstance(target, CallbackQuery):
        if not isinstance(target.message, Message):
            return
        editable_message = target.message
        if editable_message.text is None and editable_message.rich_message is None:
            content = leaderboard_content(
                kind, entries, viewer, period, snapshot.updated_at
            )
            rendered = content.as_kwargs()
            text = rendered.pop("text")
            await editable_message.answer(text, reply_markup=markup, **rendered)
            with suppress(TelegramAPIError):
                await editable_message.delete()
            return
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
    content = leaderboard_content(kind, entries, viewer, period, snapshot.updated_at)
    rendered = content.as_kwargs()
    text = rendered.pop("text")
    if isinstance(target, CallbackQuery):
        await safe_edit_text(editable_message, text, reply_markup=markup, **rendered)
    else:
        await target.answer(text, reply_markup=markup, **rendered)


@router.message(Command("leaderbord", "leaderboard"), F.chat.type == "private")
async def leaderboard_command_handler(message: Message) -> None:
    await _show_menu(message)


@router.message(Command("global"))
async def global_rank_command_handler(message: Message, session: AsyncSession) -> None:
    try:
        await _show_global_rank(message, session)
    except SQLAlchemyError:
        await message.answer("جدول سراسری رنک فعلاً در دسترس نیست.")


@router.message(
    F.chat.type == "private",
    F.text.in_({"برترین مبارز", "برترین مبارز ماهانه"}),
)
async def private_fighter_board_handler(
    message: Message, session: AsyncSession
) -> None:
    await global_rank_command_handler(message, session)


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
        if kind == "fighter":
            await _show_global_rank(message, session)
        else:
            await _show_board(
                message,
                session,
                kind,
                period=period,
                with_keyboard=False,
            )
    except SQLAlchemyError:
        await message.answer("اطلاعات برترین‌ها فعلاً در دسترس نیست.")


@router.callback_query(GlobalRankCallback.filter())
async def global_rank_callback_handler(
    callback: CallbackQuery,
    callback_data: GlobalRankCallback,
    session: AsyncSession,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    try:
        await _show_global_rank(callback, session, page=callback_data.page)
    except SQLAlchemyError:
        await callback.answer("جدول سراسری رنک فعلاً در دسترس نیست.", show_alert=True)
        return
    with suppress(TelegramAPIError):
        await callback.answer()


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
            if isinstance(callback.message, Message) and callback.message.text is None:
                await callback.message.answer(
                    "🧙 پروفایل فرمانده\n\nیکی از موارد زیر را انتخاب کن:",
                    reply_markup=profile_keyboard(owner_id=owner_id),
                )
                with suppress(TelegramAPIError):
                    await callback.message.delete()
                return
            await safe_edit_text(
                callback.message,
                "🧙 پروفایل فرمانده\n\nیکی از موارد زیر را انتخاب کن:",
                reply_markup=profile_keyboard(owner_id=owner_id),
            )
        elif callback_data.action == "menu":
            await _show_menu(callback)
        elif callback_data.action == "fighter":
            await _show_global_rank(callback, session)
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
