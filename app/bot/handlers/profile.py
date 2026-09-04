from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import ProfileCallback
from app.bot.keyboards.main_menu import MENU_SECTION_BY_LABEL, main_menu_keyboard
from app.bot.keyboards.profile import profile_keyboard
from app.bot.utils.telegram import safe_edit_text
from app.repositories.profile import ProfileSnapshot
from app.services.profile_service import ProfileNotFound, ProfileService
from app.services.school_errors import SchoolUserNotFound
from app.services.user_service import UserInactiveError, UserService

router = Router(name="profile")
profile_service = ProfileService()
user_service = UserService()

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
    banana = resources.banana if resources else 0
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
        f"🍌 موز: {_number(banana)}\n"
        f"🌟 سطح فرمانده: {_number(user.level)}\n\n"
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
        f"🍌 {_number(snapshot.loot_banana)}\n\n"
        ".━━━━━━━━━━━━━━━━━━━━━━━.\n"
        "📚 دانش و ارتباطات\n\n"
        f"✅ پاسخ‌های درست: {_number(snapshot.correct_answers)} از "
        f"{_number(snapshot.answers_count)}\n"
        f"دقت: {_accuracy(snapshot)}\n\n"
        ".━━━━━━━━━━━━━━━━━━━━━━━.\n"
        f"🤝 دوستان دعوت‌شده: {_number(snapshot.referrals_count)}\n\n"
        "✨ هر نبرد، هر پاسخ و هر دعوت، یک قدم به سمت فرمانروایی بزرگ‌تر است!"
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
            await safe_edit_text(target.message, text, reply_markup=profile_keyboard())
        except TelegramAPIError:
            await target.message.answer(text, reply_markup=profile_keyboard())
    else:
        await target.answer(text, reply_markup=profile_keyboard())


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


@router.message(Command("profile"))
@router.message(Command("stat"))
@router.message(F.text == PROFILE_LABEL)
async def profile_handler(message: Message, session: AsyncSession) -> None:
    try:
        await _show_profile(message, session)
    except (ProfileNotFound, SchoolUserNotFound, UserInactiveError):
        await _show_error(message)


@router.callback_query(ProfileCallback.filter())
async def profile_callback_handler(
    callback: CallbackQuery,
    callback_data: ProfileCallback,
    session: AsyncSession,
) -> None:
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
        await _show_profile(callback, session)
    except (ProfileNotFound, SchoolUserNotFound, UserInactiveError):
        await _show_error(callback)
        return
    await callback.answer("آمار پروفایل به‌روز شد ✨")
