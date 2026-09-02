from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import BuffetCallback
from app.bot.keyboards.buffet import buffet_keyboard
from app.bot.keyboards.main_menu import MENU_SECTION_BY_LABEL, main_menu_keyboard
from app.core.enums import ResourceType
from app.bot.states import BuffetStates
from app.services.buffet_service import (
    BuffetService,
    ConversionAmountError,
    InsufficientResource,
    InvalidBuffetConversion,
)
from app.services.user_service import UserInactiveError, UserService

router = Router(name="buffet")
buffet_service = BuffetService()
user_service = UserService()
BUFFET_LABEL = next(label for label, section in MENU_SECTION_BY_LABEL.items() if section == "buffet")
RESOURCE_LABELS = {ResourceType.COIN: "طلا", ResourceType.DIAMOND: "الماس", ResourceType.BANANA: "موز"}


def _resource_text(resources) -> str:
    return (
        f"🪙 طلا: {resources.coin}\n"
        f"💎 الماس: {resources.diamond}\n"
        f"🍌 موز: {resources.banana}"
    )


@router.message(F.text == BUFFET_LABEL)
async def buffet_handler(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    try:
        user = await user_service.get_active_by_telegram_user_id(session, message.from_user.id)
        resources = await buffet_service.resources(session, user.id)
        if resources is None:
            await message.answer("منابع شما هنوز آماده نشده است.", reply_markup=main_menu_keyboard())
            return
        await message.answer(
            "🍽 بوفه\n\nموجودی فعلی شما:\n"
            + _resource_text(resources)
            + "\n\nیک تبدیل را انتخاب کنید:",
            reply_markup=buffet_keyboard(buffet_service.options()),
        )
    except UserInactiveError:
        await message.answer("حساب شما فعال نیست.", reply_markup=main_menu_keyboard())


@router.callback_query(BuffetCallback.filter())
async def buffet_callback(
    callback: CallbackQuery,
    callback_data: BuffetCallback,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        source = ResourceType(callback_data.source)
        target = ResourceType(callback_data.target)
        user = await user_service.get_active_by_telegram_user_id(session, callback.from_user.id)
        option = buffet_service.config.buffet_conversion(source, target)
        await state.set_state(BuffetStates.convert_amount)
        await state.update_data(source=source.value, target=target.value)
        await callback.answer()
        await callback.message.answer(
            f"چه مقدار {RESOURCE_LABELS[source]} می‌خواهید تبدیل کنید؟\n"
            f"هر {option.source_amount} {RESOURCE_LABELS[source]} = "
            f"{option.target_amount} {RESOURCE_LABELS[target]}\n"
            f"مقدار باید مضربی از {option.source_amount} باشد.\n"
            f"مثال: {option.source_amount}"
        )
    except (UserInactiveError, InvalidBuffetConversion):
        await callback.answer("این تبدیل در دسترس نیست.", show_alert=True)


@router.message(BuffetStates.convert_amount, F.text)
async def buffet_exchange_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None or message.text is None:
        return
    try:
        normalized = message.text.strip().translate(
            str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬,", "01234567890123456789  ")
        ).replace(" ", "")
        amount = int(normalized)
    except ValueError:
        await message.answer("لطفاً فقط مقدار عددی وارد کنید.")
        return
    data = await state.get_data()
    try:
        source = ResourceType(data["source"])
        target = ResourceType(data["target"])
        user = await user_service.get_active_by_telegram_user_id(session, message.from_user.id)
        result = await buffet_service.exchange(
            session,
            user.id,
            source=source,
            target=target,
            source_amount=amount,
        )
    except ConversionAmountError as exc:
        await message.answer(str(exc))
        return
    except InsufficientResource as exc:
        await message.answer(str(exc))
        return
    except (UserInactiveError, InvalidBuffetConversion):
        await state.clear()
        await message.answer("این تبدیل در دسترس نیست.", reply_markup=main_menu_keyboard())
        return

    resources = await buffet_service.resources(session, user.id)
    await state.clear()
    await message.answer(
        f"✅ تبدیل انجام شد.\n"
                f"مصرف‌شده: {amount} {RESOURCE_LABELS[source]}\n"
        f"دریافت‌شده: {result.packages * result.conversion.target_amount} {RESOURCE_LABELS[target]}\n\n"
        "موجودی جدید:\n" + _resource_text(resources),
        reply_markup=main_menu_keyboard(),
    )
