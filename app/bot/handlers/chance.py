from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks_chance import ChanceBoxCallback, ChanceCardCallback
from app.bot.states import ChanceCardStates
from app.services.chance_service import AlreadyClaimed, BoxExpired, ChanceError, ChanceService, WrongCaptcha
from app.services.user_service import UserService

router = Router(name="chance")
chance_service = ChanceService()
user_service = UserService()


@router.callback_query(ChanceBoxCallback.filter())
async def claim_box(callback: CallbackQuery, callback_data: ChanceBoxCallback, session: AsyncSession) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    try:
        box, _ = await chance_service.claim_box(session, callback_data.box_id, callback.from_user.id)
    except BoxExpired:
        await callback.answer("⏰ زمان این جعبه گذشته است.", show_alert=True)
        if callback.message is not None:
            await callback.message.delete()
        return
    except AlreadyClaimed:
        await callback.answer("این جعبه قبلاً باز شده است.", show_alert=True)
        return
    except ChanceError:
        await callback.answer("امکان باز کردن جعبه وجود ندارد.", show_alert=True)
        return
    await callback.answer("جعبه را شما زودتر باز کردید! 🎉")
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"🎉 جایزه جعبه: {box.amount} {('طلا' if box.resource_type.value == 'COIN' else 'الماس')}")


@router.callback_query(ChanceCardCallback.filter())
async def start_card(callback: CallbackQuery, callback_data: ChanceCardCallback, state: FSMContext) -> None:
    await state.set_state(ChanceCardStates.waiting_captcha)
    await state.update_data(card_id=callback_data.card_id)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("کد داخل تصویر را وارد کنید:")


@router.message(ChanceCardStates.waiting_captcha)
async def verify_card(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None or not message.text:
        return
    data = await state.get_data()
    try:
        card = await chance_service.claim_card(session, int(data["card_id"]), (await user_service.get_active_by_telegram_user_id(session, message.from_user.id)).id, message.text)
    except WrongCaptcha:
        await message.answer("❌ کپچا اشتباه است. دوباره تلاش کن.")
        return
    except (AlreadyClaimed, ChanceError):
        await state.clear()
        await message.answer("این کارت دیگر قابل استفاده نیست.")
        return
    await state.clear()
    await message.answer(f"✅ پاسخ صحیح بود؛ {card.amount} {('طلا' if card.resource_type.value == 'COIN' else 'الماس')} دریافت کردی.")
