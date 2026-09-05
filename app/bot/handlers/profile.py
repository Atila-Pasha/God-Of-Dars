from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import LevelConfirmationCallback, ProfileCallback
from app.bot.keyboards.main_menu import MENU_SECTION_BY_LABEL, main_menu_keyboard
from app.bot.keyboards.profile import level_confirmation_keyboard, profile_keyboard
from app.bot.utils.telegram import safe_edit_text
from app.repositories.profile import ProfileSnapshot
from app.services.level_service import LevelService
from app.services.profile_service import ProfileNotFound, ProfileService
from app.services.school_errors import (
    InsufficientCoins,
    MaxLevelReached,
    OperationNotConfigured,
    SchoolUserNotFound,
)
from app.services.user_service import UserInactiveError, UserService

router = Router(name="profile")
profile_service = ProfileService()
user_service = UserService()
level_service = LevelService()

PROFILE_LABEL = next(
    label for label, section in MENU_SECTION_BY_LABEL.items() if section == "profile"
)


def _number(value: int) -> str:
    return f"{value:,}".translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _name(snapshot: ProfileSnapshot) -> str:
    user = snapshot.user
    full_name = " ".join(part for part in (user.first_name, user.last_name) if part)
    return full_name or "فرمانده بی‌نام"


def _username(snapshot: ProfileSnapshot) -> str:
    username = snapshot.user.username
    return f"@{username}" if username else "ندارد"


def _date(value: datetime | None) -> str:
    if value is None:
        return "نامشخص"
    date_value = value if value.tzinfo is None else value.astimezone()
    return date_value.strftime("%Y/%m/%d")


def _accuracy(snapshot: ProfileSnapshot) -> str:
    if snapshot.answers_count == 0:
        return "هنوز رکوردی ثبت نشده"
    percent = round(snapshot.correct_answers / snapshot.answers_count * 100)
    return f"{_number(percent)}٪"


def _profile_text(snapshot: ProfileSnapshot) -> str:
    user = snapshot.user
    resources = user.resources
    castle = user.castle
    defense_power = castle.defense.defense_power if castle and castle.defense else 0

    coin = resources.coin if resources else 0
    diamond = resources.diamond if resources else 0
    xp = resources.banana if resources else 0
    castle_level = castle.level if castle else 0
    castle_strength = castle.strength if castle else 0

    return (
        ".━━━━━━ 🧙 پروفایل فرمانده ━━━━━━.\n"
        f" 👤نام: {_name(snapshot)}\n"
        f" 📎 نام کاربری: {_username(snapshot)}\n"
        f" 📅 عضو از: {_date(user.created_at)}\n"
        f"🌟 سطح فرمانده: {_number(user.level)}\n\n"
        ".━━━━━━━━━━━━━━━━━━━━━━━.\n"
        "💰 کیف دارایی\n\n"
        f"🪙 سکه: {_number(coin)}\n"
        f"💎 الماس: {_number(diamond)}\n"
        f"🍌 موز: {_number(xp)}\n"
        "\n"
        ".━━━━━━━━━━━━━━━━━━━━━━━.\n"
        "🏰 قلمرو و مدرسه\n\n"
        f"🏯 سطح دژ: {_number(castle_level)}\n"
        f"❤️ استحکام دژ: {_number(castle_strength)}\n"
        f"🛡 قدرت دفاع: {_number(defense_power)}\n"
        f"👨‍🏫 دبیرها: {_number(snapshot.active_teachers_count)} فعال از "
        f"{_number(snapshot.teachers_count)}\n\n"
        ".━━━━━━━━━━━━━━━━━━━━━━━.\n"
        "⚔️ کارنامه نبرد\n\n"
        f"⚔️ حمله‌های انجام‌شده: {_number(snapshot.attacks_sent)}\n"
        f"🏆 حمله‌های موفق: {_number(snapshot.successful_attacks)}\n"
        f"🎯 حمله‌های در انتظار: {_number(snapshot.pending_attacks)}\n"
        f"🎖 حمله‌های دریافتی: {_number(snapshot.attacks_received)}\n"
        f"💥 آسیب واردشده: {_number(snapshot.damage_dealt)}\n\n"
        ".━━━━━━━━━━━━━━━━━━━━━━━.\n"
        "غنیمت‌های ثبت‌شده:\n\n"
        f"🪙 {_number(snapshot.loot_coin)}\n"
        f"💎 {_number(snapshot.loot_diamond)}\n"
        f"🍌 موز دریافتی از حمله: {_number(snapshot.loot_banana)}\n\n"
        ".━━━━━━━━━━━━━━━━━━━━━━━.\n"
        "📚 دانش و ارتباطات\n\n"
        f"✅ پاسخ‌های درست: {_number(snapshot.correct_answers)} از "
        f"{_number(snapshot.answers_count)}\n"
        f"دقت: {_accuracy(snapshot)}\n\n"
        ".━━━━━━━━━━━━━━━━━━━━━━━.\n"
        f"🤝 دوستان دعوت‌شده: {_number(snapshot.referrals_count)}\n\n"
        "✨ هر نبرد، هر پاسخ و هر دعوت، یک قدم به سمت فرمانروایی بزرگ‌تر است!"
    )


def _profile_menu_text() -> str:
    return "🧙 پروفایل فرمانده\n\nیکی از موارد زیر را انتخاب کن:"


def _profile_markup(target: Message | CallbackQuery):
    chat = (
        target.message.chat
        if isinstance(target, CallbackQuery) and target.message is not None
        else getattr(target, "chat", None)
    )
    owner_id = target.from_user.id if target.from_user is not None else 0
    return profile_keyboard(
        include_delete=getattr(chat, "type", "private") in {"group", "supergroup"},
        owner_id=owner_id,
    )


def _profile_identity_text(snapshot: ProfileSnapshot) -> str:
    user = snapshot.user
    return (
        "👤 اطلاعات پروفایل\n\n"
        f"نام: {_name(snapshot)}\n"
        f"نام کاربری: {_username(snapshot)}\n"
        f"عضویت از: {_date(user.created_at)}\n"
        f"سطح فرمانده: {_number(user.level)}\n"
        f"تعداد دبیرها: {_number(snapshot.teachers_count)}\n"
        f"دبیرهای فعال: {_number(snapshot.active_teachers_count)}"
    )


def _profile_war_text(snapshot: ProfileSnapshot) -> str:
    return (
        "⚔️ اطلاعات جنگ\n\n"
        f"حمله‌های انجام‌شده: {_number(snapshot.attacks_sent)}\n"
        f"حمله‌های موفق: {_number(snapshot.successful_attacks)}\n"
        f"حمله‌های در انتظار: {_number(snapshot.pending_attacks)}\n"
        f"حمله‌های دریافتی: {_number(snapshot.attacks_received)}\n"
        f"آسیب واردشده: {_number(snapshot.damage_dealt)}\n\n"
        "غنیمت‌های ثبت‌شده:\n"
        f"سکه: {_number(snapshot.loot_coin)}\n"
        f"الماس: {_number(snapshot.loot_diamond)}\n"
        f"موز دریافتی از حمله: {_number(snapshot.loot_banana)}"
    )


def _profile_assets_text(snapshot: ProfileSnapshot) -> str:
    user = snapshot.user
    resources = user.resources
    castle = user.castle
    defense_power = castle.defense.defense_power if castle and castle.defense else 0
    return (
        "🏰 دارایی و قلمرو\n\n"
        f"سکه: {_number(resources.coin if resources else 0)}\n"
        f"الماس: {_number(resources.diamond if resources else 0)}\n"
        f"موز: {_number(resources.banana if resources else 0)}\n\n"
        f"سطح دژ: {_number(castle.level if castle else 0)}\n"
        f"استحکام دژ: {_number(castle.strength if castle else 0)}\n"
        f"قدرت دفاع: {_number(defense_power)}"
    )


def _profile_knowledge_text(snapshot: ProfileSnapshot) -> str:
    return (
        "📚 دانش و دعوت‌ها\n\n"
        f"پاسخ‌های درست: {_number(snapshot.correct_answers)} از "
        f"{_number(snapshot.answers_count)}\n"
        f"دقت: {_accuracy(snapshot)}\n"
        f"دوستان دعوت‌شده: {_number(snapshot.referrals_count)}"
    )


async def _user_id(session: AsyncSession, target: Message | CallbackQuery) -> int:
    if target.from_user is None:
        raise ProfileNotFound
    user = await user_service.get_active_by_telegram_user_id(
        session, target.from_user.id
    )
    return user.id


async def _show_profile(target: Message | CallbackQuery, session: AsyncSession) -> None:
    snapshot = await profile_service.snapshot(session, await _user_id(session, target))
    text = _profile_text(snapshot)
    if isinstance(target, CallbackQuery):
        if target.message is None:
            return
        try:
            await safe_edit_text(
                target.message, text, reply_markup=_profile_markup(target)
            )
        except TelegramAPIError:
            await target.message.answer(text, reply_markup=_profile_markup(target))
    else:
        await target.answer(text, reply_markup=_profile_markup(target))


async def _show_profile_menu(target: Message | CallbackQuery) -> None:
    """Show profile actions without loading and dumping the full statistics."""
    text = _profile_menu_text()
    if isinstance(target, CallbackQuery):
        if target.message is None:
            return
        try:
            await safe_edit_text(
                target.message, text, reply_markup=_profile_markup(target)
            )
        except TelegramAPIError:
            await target.message.answer(text, reply_markup=_profile_markup(target))
    else:
        await target.answer(text, reply_markup=_profile_markup(target))


async def _show_profile_section(
    target: Message | CallbackQuery,
    session: AsyncSession,
    section: str,
) -> None:
    snapshot = await profile_service.snapshot(session, await _user_id(session, target))
    text = {
        "profile": _profile_identity_text(snapshot),
        "war": _profile_war_text(snapshot),
        "assets": _profile_assets_text(snapshot),
        "knowledge": _profile_knowledge_text(snapshot),
    }[section]
    if isinstance(target, CallbackQuery):
        if target.message is None:
            return
        await safe_edit_text(target.message, text, reply_markup=_profile_markup(target))
    else:
        await target.answer(text, reply_markup=_profile_markup(target))


async def _show_error(target: Message | CallbackQuery) -> None:
    text = "پروفایل شما فعلاً در دسترس نیست؛ لطفاً دوباره تلاش کنید."
    if isinstance(target, CallbackQuery):
        await target.answer(text, show_alert=True)
    else:
        reply_markup = (
            ReplyKeyboardRemove()
            if target.chat.type in {"group", "supergroup"}
            else main_menu_keyboard()
        )
        await target.answer(text, reply_markup=reply_markup)


async def _show_level_upgrade(target: CallbackQuery, session: AsyncSession) -> None:
    user_id = await _user_id(session, target)
    snapshot = await profile_service.snapshot(session, user_id)
    cost = level_service.upgrade_cost(snapshot.user.level)
    resources = snapshot.user.resources
    xp = resources.banana if resources else 0
    text = (
        f"⬆️ ارتقای سطح فرمانده\n\n"
        f"سطح فعلی: {_number(snapshot.user.level)}\n"
        f"سطح بعدی: {_number(snapshot.user.level + 1)}\n"
        f"هزینه: {_number(cost)} موز\n"
        f"موز شما: {_number(xp)}\n\n"
        "آیا ارتقای سطح را تأیید می‌کنی؟"
    )
    await safe_edit_text(
        target.message, text, reply_markup=level_confirmation_keyboard()
    )


@router.message(Command("profile"))
@router.message(Command("stat"))
@router.message(Command("profile_info"))
@router.message(Command("war"))
@router.message(Command("assets"))
@router.message(Command("knowledge"))
@router.message(F.text == PROFILE_LABEL)
@router.message(
    F.text.in_(
        {
            "اطلاعات پروفایل",
            "اطلاعات جنگ",
            "اطلاعات دارایی",
            "اطلاعات دانش",
        }
    )
)
async def profile_handler(message: Message, session: AsyncSession) -> None:
    try:
        # The profile menu is an action hub. Keep /stat as the explicit
        # shortcut for the detailed report for backwards compatibility.
        message_text = (getattr(message, "text", None) or "").strip()
        command_name = (
            message_text.split(maxsplit=1)[0].split("@", 1)[0].removeprefix("/")
            if message_text
            else ""
        )
        section = {
            "اطلاعات پروفایل": "profile",
            "اطلاعات جنگ": "war",
            "اطلاعات دارایی": "assets",
            "اطلاعات دانش": "knowledge",
            "profile_info": "profile",
            "war": "war",
            "assets": "assets",
            "knowledge": "knowledge",
        }.get(message_text, None)
        if section is None:
            section = {
                "profile_info": "profile",
                "war": "war",
                "assets": "assets",
                "knowledge": "knowledge",
            }.get(command_name)
        if section is not None:
            await _show_profile_section(message, session, section)
        elif not message_text or command_name == "stat":
            await _show_profile(message, session)
        else:
            await _show_profile_menu(message)
    except (ProfileNotFound, SchoolUserNotFound, UserInactiveError):
        await _show_error(message)


@router.callback_query(ProfileCallback.filter())
async def profile_callback_handler(
    callback: CallbackQuery,
    callback_data: ProfileCallback,
    session: AsyncSession,
) -> None:
    if callback_data.action == "delete":
        if callback.from_user is None or callback.message is None:
            return
        if callback.from_user.id != callback_data.owner_id:
            await callback.answer(
                "فقط درخواست‌کننده اطلاعات می‌تواند این پیام را حذف کند.", show_alert=True
            )
            return
        await callback.answer("پیام اطلاعات حذف شد.")
        try:
            await callback.message.delete()
        except TelegramAPIError:
            # The message may already have been removed or the bot may lack
            # delete permission; do not turn that into a polling error.
            pass
        return

    if callback_data.action == "back":
        if callback.message is not None:
            await callback.message.answer(
                "منوی اصلی آماده‌ست؛ فرمانده، انتخاب با توست 👑",
                reply_markup=(
                    ReplyKeyboardRemove()
                    if callback.message.chat.type in {"group", "supergroup"}
                    else main_menu_keyboard()
                ),
            )
        await callback.answer()
        return

    try:
        if callback_data.action == "upgrade":
            await callback.answer()
            await _show_level_upgrade(callback, session)
            return
        if callback_data.action == "info":
            # Compatibility with older profile messages: the former single
            # "اطلاعات کاربری" button now opens only the profile section.
            await _show_profile_section(callback, session, "profile")
        elif callback_data.action in {"profile", "war", "assets", "knowledge"}:
            await _show_profile_section(callback, session, callback_data.action)
        else:
            await _show_profile_menu(callback)
    except (ProfileNotFound, SchoolUserNotFound, UserInactiveError):
        await _show_error(callback)
        return
    await callback.answer()


@router.callback_query(LevelConfirmationCallback.filter())
async def level_confirmation_handler(
    callback: CallbackQuery,
    callback_data: LevelConfirmationCallback,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    if callback_data.decision == "cancel":
        await callback.answer("ارتقا لغو شد.")
        await _show_profile_menu(callback)
        return
    await callback.answer()
    try:
        user_id = await _user_id(session, callback)
        user = await level_service.upgrade(session, user_id)
        await _show_profile(callback, session)
        await callback.message.answer(f"سطح شما به {user.level} رسید.")
    except InsufficientCoins:
        await callback.message.answer("XP کافی ندارید.")
    except MaxLevelReached:
        await callback.message.answer("به بالاترین سطح تنظیم‌شده رسیده‌اید.")
    except (OperationNotConfigured, SchoolUserNotFound, UserInactiveError):
        await callback.message.answer("ارتقای سطح فعلاً در دسترس نیست.")
