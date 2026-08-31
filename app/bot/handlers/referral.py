from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.main_menu import MENU_SECTION_BY_LABEL, main_menu_keyboard
from app.bot.keyboards.referral import referral_keyboard
from app.services.referral_service import ReferralService
from app.services.user_service import UserInactiveError, UserService

router = Router(name="referral")
referral_service = ReferralService()
user_service = UserService()

REFERRAL_LABEL = next(
    label
    for label, section in MENU_SECTION_BY_LABEL.items()
    if section == "referral"
)


async def _invite_link(message: Message, user_id: int) -> str | None:
    if message.bot is None:
        return None
    try:
        bot_user = await message.bot.me()
    except TelegramAPIError:
        return None
    if not bot_user.username:
        return None
    return (
        f"https://t.me/{bot_user.username}"
        f"?start={referral_service.payload_for(user_id)}"
    )


@router.message(Command("referral"))
@router.message(F.text == REFERRAL_LABEL)
async def referral_handler(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    try:
        user = await user_service.get_active_by_telegram_user_id(
            session, message.from_user.id
        )
        count = await referral_service.count(session, user.id)
        invite_link = await _invite_link(message, user.id)
        link_text = invite_link or "لینک دعوت فعلاً قابل تولید نیست."
        await message.answer(
            "👥 دعوت دوستان\n\n"
            "دوستت را دعوت کن و با هم بازی کنید.\n\n"
            f"🔗 لینک اختصاصی شما:\n{link_text}\n\n"
            f"👤 تعداد دعوت‌های ثبت‌شده: {count}",
            reply_markup=referral_keyboard(invite_link),
        )
    except UserInactiveError:
        await message.answer(
            "حساب شما فعال نیست.", reply_markup=main_menu_keyboard()
        )
