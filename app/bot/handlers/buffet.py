from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import BuffetCallback, BuffetMenuCallback, ShieldCallback
from app.bot.keyboards.buffet import (
    buffet_cancel_keyboard,
    buffet_keyboard,
    buffet_menu_keyboard,
    shield_catalog_keyboard,
    shield_inventory_keyboard,
)
from app.bot.keyboards.main_menu import MENU_SECTION_BY_LABEL, main_menu_keyboard
from app.bot.keyboards.school import teacher_catalog_keyboard
from app.bot.states import BuffetStates
from app.bot.utils.telegram import safe_edit_text
from app.core.enums import ResourceType
from app.services.buffet_service import (
    BuffetService,
    ConversionAmountError,
    InsufficientResource,
    InvalidBuffetConversion,
)
from app.services.school_errors import (
    InsufficientCoins,
    SchoolError,
    SchoolUserNotFound,
    ShieldLocked,
    ShieldNotFound,
    ShieldNotPurchasable,
)
from app.services.shield_service import ShieldService
from app.services.teacher_service import TeacherService
from app.services.user_service import UserInactiveError, UserService

router = Router(name="buffet")
buffet_service = BuffetService()
user_service = UserService()
shield_service = ShieldService()
teacher_service = TeacherService()
BUFFET_LABEL = next(
    label for label, section in MENU_SECTION_BY_LABEL.items() if section == "buffet"
)
RESOURCE_LABELS = {
    ResourceType.COIN: "طلا",
    ResourceType.DIAMOND: "الماس",
}


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("buy"))
@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.regexp(r"^\s*خرید(?:\s+\S.*)?$"),
)
async def group_purchase_message(
    message: Message,
    session: AsyncSession,
    command: CommandObject | None = None,
) -> None:
    if message.from_user is None or not message.text:
        return
    if len(message.text.split(maxsplit=1)) != 2:
        await message.answer("فرمت خرید: خرید نام دبیر یا خرید نام سپر")
        return
    name = (command.args if command is not None else None) or message.text.partition(" ")[2]
    name = name.strip()
    if not name:
        await message.answer("فرمت خرید: /buy نام دبیر یا /buy نام سپر")
        return
    try:
        user = await user_service.get_active_by_telegram_user_id(
            session, message.from_user.id
        )
        teacher_catalog = await teacher_service.catalog(session, user.id)
        teacher = next(
            (item for item in teacher_catalog if item.name.casefold() == name.casefold()),
            None,
        )
        if teacher is not None:
            purchased = await teacher_service.buy(session, user.id, teacher.id)
            await message.answer(
                f"دبیر «{purchased.teacher.name}» با موفقیت خریداری شد."
            )
            return

        shield_catalog = await shield_service.catalog(session, player_level=user.level)
        shield = next(
            (item for item in shield_catalog if item.name.casefold() == name.casefold()),
            None,
        )
        if shield is not None:
            purchased = await shield_service.buy(session, user.id, shield.id)
            await message.answer(
                f"سپر «{purchased.shield.name}» خریداری شد؛ "
                f"{purchased.quantity} عدد در موجودی دارید."
            )
            return
        await message.answer("دبیر یا سپری با این نام برای سطح شما پیدا نشد.")
    except InsufficientCoins:
        await message.answer("سکه کافی برای این خرید ندارید.")
    except SchoolError:
        await message.answer("این خرید در حال حاضر امکان‌پذیر نیست.")


def _resource_text(resources) -> str:
    return (
        f"🪙 طلا: {resources.coin}\n"
        f"💎 الماس: {resources.diamond}"
    )


@router.message(F.text == BUFFET_LABEL)
async def buffet_handler(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    try:
        await user_service.get_active_by_telegram_user_id(session, message.from_user.id)
        await message.answer(
            "🍽 بوفه\n\nاز بخش‌های زیر یکی را انتخاب کنید:",
            reply_markup=buffet_menu_keyboard(),
        )
    except (UserInactiveError, SchoolUserNotFound):
        await message.answer("حساب شما فعال نیست.", reply_markup=main_menu_keyboard())


async def _buffet_menu_view(
    target: Message | CallbackQuery, session: AsyncSession
) -> None:
    text = "🍽 بوفه\n\nاز بخش‌های زیر یکی را انتخاب کنید:"
    if isinstance(target, CallbackQuery) and target.message is not None:
        # Reply keyboards cannot be attached to editMessageText. Send a fresh
        # message so Telegram replaces the user's keyboard at the bottom.
        await target.message.answer(text, reply_markup=buffet_menu_keyboard())
    else:
        await target.answer(text, reply_markup=buffet_menu_keyboard())


@router.message(F.text.in_({"تبدیل منابع", "🔄 تبدیل منابع"}))
async def buffet_conversion_message(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    if message.from_user is None:
        return
    try:
        await state.clear()
        user = await user_service.get_active_by_telegram_user_id(
            session, message.from_user.id
        )
        resources = await buffet_service.resources(session, user.id)
        if resources is None:
            raise UserInactiveError
        await message.answer(
            "🔄 تبدیل منابع\n\nموجودی فعلی شما:\n"
            + _resource_text(resources)
            + "\n\nیک تبدیل را انتخاب کنید:",
            reply_markup=buffet_keyboard(buffet_service.options()),
        )
    except (UserInactiveError, SchoolUserNotFound):
        await message.answer("حساب شما فعال نیست.", reply_markup=main_menu_keyboard())


@router.message(F.text.in_({"خرید سپر", "🛡 خرید سپر"}))
async def buffet_shields_message(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    if message.from_user is None:
        return
    try:
        await state.clear()
        await _shields_view(message, session)
    except (UserInactiveError, SchoolUserNotFound):
        await message.answer("حساب شما فعال نیست.", reply_markup=main_menu_keyboard())


@router.message(F.text.in_({"خرید دبیر", "👨‍🏫 خرید دبیر"}))
async def buffet_teachers_message(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    if message.from_user is None:
        return
    try:
        await state.clear()
        await user_service.get_active_by_telegram_user_id(session, message.from_user.id)
        await _teacher_shop_view(message, session)
    except (UserInactiveError, SchoolUserNotFound):
        await message.answer("حساب شما فعال نیست.", reply_markup=main_menu_keyboard())


async def _teacher_shop_view(target: Message | CallbackQuery, session: AsyncSession) -> None:
    user = await user_service.get_active_by_telegram_user_id(
        session, target.from_user.id
    )
    catalog = await teacher_service.catalog(session, user.id)
    text = "👨‍🏫 خرید دبیر\n\nدبیر موردنظر را انتخاب کنید:"
    markup = teacher_catalog_keyboard(
        catalog, player_level=user.level, back_action="back_buffet", origin="buffet"
    )
    if isinstance(target, CallbackQuery) and target.message is not None:
        await safe_edit_text(target.message, text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(F.text.in_({"منوی اصلی", "لغو", "🔙 منوی اصلی", "❌ لغو"}))
async def buffet_back_to_main(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("به منوی اصلی برگشتید.", reply_markup=main_menu_keyboard())


async def _conversion_view(target: CallbackQuery, session: AsyncSession) -> None:
    user = await user_service.get_active_by_telegram_user_id(
        session, target.from_user.id
    )
    resources = await buffet_service.resources(session, user.id)
    if resources is None:
        raise UserInactiveError
    text = (
        "🔄 تبدیل منابع\n\nموجودی فعلی شما:\n"
        + _resource_text(resources)
        + "\n\nیک تبدیل را انتخاب کنید:"
    )
    await safe_edit_text(
        target.message, text, reply_markup=buffet_keyboard(buffet_service.options())
    )


async def _shields_view(target: Message | CallbackQuery, session: AsyncSession) -> None:
    user = await user_service.get_active_by_telegram_user_id(
        session, target.from_user.id
    )
    owned = await shield_service.list_owned(session, user.id)
    catalog = await shield_service.catalog(session, player_level=user.level)
    lines = [f"🛡 سپرهای بوفه\n\n🎖 سطح شما: {user.level}"]
    if owned:
        lines.append("\n📦 موجودی شما:")
        for item in owned:
            state = "✅ فعال" if item.is_equipped else "⚪ آماده‌سازی"
            lines.append(
                f"\n{state} — {item.shield.name} × {item.quantity}"
                f"\nکاهش آسیب: {item.shield.reduction_percent}% + {item.shield.flat_absorption} واحد"
            )
    else:
        lines.append("\nهنوز سپری ندارید.")
    lines.append("\n\nسپرهای قابل خرید در سطح شما:")
    if not catalog:
        lines.append("\nفعلاً سپری برای سطح شما تعریف نشده است.")
    else:
        for shield in catalog:
            lines.append(
                f"\n🛡 {shield.name} — {shield.purchase_price} سکه"
                f"\nکاهش آسیب: {shield.reduction_percent}% + {shield.flat_absorption} واحد"
                + (f"\n{shield.description}" if shield.description else "")
            )
    reply_markup = (
        shield_catalog_keyboard(catalog, owned)
        if catalog
        else shield_inventory_keyboard(owned)
    )
    if isinstance(target, CallbackQuery) and target.message is not None:
        await safe_edit_text(target.message, "".join(lines), reply_markup=reply_markup)
    else:
        await target.answer("".join(lines), reply_markup=reply_markup)


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
        await user_service.get_active_by_telegram_user_id(
            session, callback.from_user.id
        )
        option = buffet_service.config.buffet_conversion(source, target)
        await state.set_state(BuffetStates.convert_amount)
        await state.update_data(source=source.value, target=target.value)
        await callback.answer()
        await callback.message.answer(
            f"چه مقدار {RESOURCE_LABELS[source]} می‌خواهید تبدیل کنید؟\n"
            f"هر {option.source_amount} {RESOURCE_LABELS[source]} = "
            f"{option.target_amount} {RESOURCE_LABELS[target]}\n"
            f"مقدار باید مضربی از {option.source_amount} باشد.\n"
            f"مثال: {option.source_amount}",
            reply_markup=buffet_cancel_keyboard(),
        )
    except (UserInactiveError, SchoolUserNotFound, InvalidBuffetConversion):
        await callback.answer("این تبدیل در دسترس نیست.", show_alert=True)


@router.callback_query(BuffetMenuCallback.filter())
async def buffet_menu_callback(
    callback: CallbackQuery,
    callback_data: BuffetMenuCallback,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        if callback_data.action == "convert":
            await _conversion_view(callback, session)
        elif callback_data.action == "teachers":
            await _teacher_shop_view(callback, session)
        elif callback_data.action == "shields":
            await _shields_view(callback, session)
        else:
            await state.clear()
            await callback.message.answer(
                "به منوی اصلی برگشتید.", reply_markup=main_menu_keyboard()
            )
        await callback.answer()
    except (UserInactiveError, SchoolUserNotFound, ShieldNotFound):
        await callback.answer("اطلاعات بوفه در دسترس نیست.", show_alert=True)


@router.callback_query(ShieldCallback.filter())
async def shield_callback(
    callback: CallbackQuery,
    callback_data: ShieldCallback,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        user = await user_service.get_active_by_telegram_user_id(
            session, callback.from_user.id
        )
        if callback_data.action == "back":
            await _buffet_menu_view(callback, session)
        elif callback_data.action == "equip":
            item = await shield_service.equip(session, user.id, callback_data.shield_id)
            await _shields_view(callback, session)
            await callback.answer(f"سپر «{item.shield.name}» فعال شد.")
            return
        else:
            shield = await shield_service.get_shield(session, callback_data.shield_id)
            if shield is None:
                raise ShieldNotFound
            purchase = await shield_service.buy(session, user.id, shield.id)
            await _shields_view(callback, session)
            await callback.answer(
                f"سپر «{purchase.shield.name}» خریداری شد؛ {purchase.quantity} عدد در موجودی.",
                show_alert=True,
            )
            return
        await callback.answer()
    except InsufficientCoins:
        await callback.answer("سکه کافی ندارید.", show_alert=True)
    except ShieldLocked:
        await callback.answer("این سپر برای سطح شما باز نشده است.", show_alert=True)
    except (
        ShieldNotFound,
        ShieldNotPurchasable,
        UserInactiveError,
        SchoolUserNotFound,
    ):
        await callback.answer("این سپر در دسترس نیست.", show_alert=True)


@router.message(BuffetStates.convert_amount, F.text)
async def buffet_exchange_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None or message.text is None:
        return
    try:
        normalized = (
            message.text.strip()
            .translate(
                str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬,", "01234567890123456789  ")
            )
            .replace(" ", "")
        )
        amount = int(normalized)
    except ValueError:
        await message.answer("لطفاً فقط مقدار عددی وارد کنید.")
        return
    data = await state.get_data()
    try:
        source = ResourceType(data["source"])
        target = ResourceType(data["target"])
        user = await user_service.get_active_by_telegram_user_id(
            session, message.from_user.id
        )
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
        await message.answer(
            "این تبدیل در دسترس نیست.", reply_markup=main_menu_keyboard()
        )
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
