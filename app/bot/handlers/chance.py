from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.banners import MARKDOWN_V2, emoji, escape
from app.bot.callbacks_chance import (
    ChanceBoxCallback,
    ChanceBoxCaptchaCallback,
    ChanceCardCallback,
)
from app.bot.states import ChanceCardStates
from app.models.chance_card import ChanceCard
from app.services.chance_service import (
    AlreadyAttempted,
    AlreadyClaimed,
    BoxExpired,
    CardExpired,
    ChanceError,
    ChanceService,
    WrongCaptcha,
)
from app.services.school_errors import SchoolUserNotFound
from app.services.user_service import UserInactiveError, UserService

router = Router(name="chance")
chance_service = ChanceService()
user_service = UserService()


def _user_display_name(user) -> str:
    name = " ".join(
        part
        for part in (
            getattr(user, "first_name", None),
            getattr(user, "last_name", None),
        )
        if part
    )
    return name or (
        f"@{user.username}" if getattr(user, "username", None) else str(user.id)
    )


def _resource_label(resource_type) -> str:
    return {
        "COIN": "طلا",
        "DIAMOND": "الماس",
        "BANANA": "موز",
    }.get(resource_type.value, resource_type.value)


@router.callback_query(ChanceBoxCallback.filter())
@router.callback_query(ChanceBoxCaptchaCallback.filter())
async def claim_box(
    callback: CallbackQuery,
    callback_data: ChanceBoxCallback | ChanceBoxCaptchaCallback,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    try:
        box, _ = await chance_service.claim_box(
            session,
            callback_data.box_id,
            callback.from_user.id,
            getattr(callback_data, "answer", None),
        )
        # The reward must remain durable even if editing the Telegram message
        # fails after the winner has been selected.
        await session.commit()
    except BoxExpired:
        await callback.answer("⏰ زمان این جعبه گذشته است.", show_alert=True)
        if isinstance(callback.message, Message):
            with suppress(TelegramAPIError):
                await callback.message.delete()
        return
    except AlreadyClaimed:
        await callback.answer("این جعبه قبلاً باز شده است.", show_alert=True)
        return
    except WrongCaptcha:
        await session.commit()
        await callback.answer(
            "پاسخ اشتباه بود؛ برای این جعبه فقط یک فرصت داشتی.", show_alert=True
        )
        return
    except AlreadyAttempted:
        await callback.answer("قبلاً به کپچای این جعبه پاسخ دادی.", show_alert=True)
        return
    except ChanceError:
        await callback.answer("امکان باز کردن جعبه وجود ندارد.", show_alert=True)
        return
    await callback.answer("جعبه را شما زودتر باز کردید! 🎉")
    if isinstance(callback.message, Message):
        try:
            await callback.message.answer(
                f"{emoji('6039496463749223185', '🎉')} فرمانده "
                f"«{escape(_user_display_name(callback.from_user))}» "
                f"جعبه شانس را باز کرد و "
                f"{escape(box.amount)} {escape(_resource_label(box.resource_type))} "
                "دریافت کرد\\!",
                reply_to_message_id=callback.message.message_id,
                parse_mode=MARKDOWN_V2,
            )
        finally:
            try:
                await callback.message.delete()
            except TelegramAPIError:
                pass  # The persistent cleanup worker retries this deletion.
            else:
                box.telegram_message_id = None
                await session.commit()


@router.callback_query(ChanceCardCallback.filter())
async def start_card(
    callback: CallbackQuery,
    callback_data: ChanceCardCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    try:
        user = await user_service.get_active_by_telegram_user_id(
            session, callback.from_user.id
        )
    except (SchoolUserNotFound, UserInactiveError):
        await callback.answer("حساب کاربری شما فعال نیست.", show_alert=True)
        return
    card = await session.get(ChanceCard, callback_data.card_id)
    if card is None or card.user_id != user.id or card.is_claimed:
        await callback.answer("این کارت دیگر قابل استفاده نیست.", show_alert=True)
        return
    if chance_service.card_expires_at(card) <= datetime.now(UTC):
        await callback.answer("مهلت این کارت شانس تمام شده است.", show_alert=True)
        return
    await state.set_state(ChanceCardStates.waiting_captcha)
    await state.update_data(card_id=callback_data.card_id)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("پاسخ مسئله را فقط با عدد بفرستید:")


@router.message(ChanceCardStates.waiting_captcha)
async def verify_card(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    if message.from_user is None or not message.text:
        return
    data = await state.get_data()
    try:
        card = await chance_service.claim_card(
            session,
            int(data["card_id"]),
            (
                await user_service.get_active_by_telegram_user_id(
                    session, message.from_user.id
                )
            ).id,
            message.text,
        )
        await session.commit()
    except WrongCaptcha:
        await session.commit()
        await state.clear()
        await message.answer("❌ پاسخ اشتباه بود؛ این کارت فقط یک فرصت داشت.")
        return
    except CardExpired:
        await state.clear()
        await message.answer("مهلت این کارت شانس تمام شده است.")
        return
    except (AlreadyClaimed, ChanceError):
        await state.clear()
        await message.answer("این کارت دیگر قابل استفاده نیست.")
        return
    await state.clear()
    await message.answer(
        f"✅ پاسخ صحیح بود؛ {card.amount} {_resource_label(card.resource_type)} دریافت کردی."
    )
