from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.banners import (
    MARKDOWN_V2,
    bold,
    emoji,
    escape,
    purchase_banner,
    section_entry_banner,
)
from app.bot.callbacks import (
    BuffetCallback,
    BuffetMenuCallback,
    ShieldCallback,
    ShieldPurchaseCallback,
)
from app.bot.keyboards.buffet import (
    SHIELD_FALLBACKS,
    SHIELD_ICONS,
    buffet_cancel_keyboard,
    buffet_keyboard,
    buffet_menu_keyboard,
    shield_catalog_keyboard,
    shield_inventory_keyboard,
    shield_purchase_confirmation,
)
from app.bot.keyboards.main_menu import (
    MENU_SECTION_BY_LABEL,
    main_menu_keyboard,
)
from app.bot.keyboards.school import (
    confirmation_keyboard,
    teacher_catalog_page_keyboard,
)
from app.bot.states import BuffetStates
from app.bot.teacher_lookup import matching_teachers
from app.bot.utils.telegram import (
    group_user_request,
    report_group_purchase_failure,
    safe_edit_text,
)
from app.core.enums import ResourceType
from app.services.buffet_service import (
    BuffetService,
    ConversionAmountError,
    InsufficientResource,
    InvalidBuffetConversion,
)
from app.services.school_errors import (
    InsufficientCoins,
    InsufficientDiamonds,
    ResourceNotFound,
    SchoolError,
    SchoolUserNotFound,
    ShieldAlreadyActive,
    ShieldLocked,
    ShieldNotFound,
    ShieldNotPurchasable,
    TeacherAlreadyOwned,
    TeacherLimitReached,
    TeacherLocked,
    TeacherNotFound,
    TeacherNotPurchasable,
    TeacherSlotLocked,
)
from app.services.shield_service import (
    SHIELD_DAILY_LIMITS,
    ShieldDailyLimitReached,
    ShieldService,
)
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
RESOURCE_EMOJIS = {
    ResourceType.COIN: "🪙",
    ResourceType.DIAMOND: "💎",
}


def _resource_display(resource: ResourceType) -> str:
    return RESOURCE_EMOJIS[resource]


async def _delete_group_purchase_prompt(callback: CallbackQuery) -> None:
    message = callback.message
    if not isinstance(message, Message) or message.chat.type not in {
        "group",
        "supergroup",
    }:
        return
    with suppress(TelegramAPIError):
        await message.delete()


def _shield_currency(shield) -> str:
    return "الماس" if shield.purchase_resource is ResourceType.DIAMOND else "طلا"


async def _answer_shield_purchase_error(
    callback: CallbackQuery, source_message: Message | None, reason: str
) -> None:
    reported = await report_group_purchase_failure(
        callback,
        item_type="سپر",
        reason=reason,
        source_message=source_message,
    )
    await callback.answer(
        "خرید ناموفق بود." if reported else reason,
        show_alert=not reported,
    )


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.regexp(r"^\s*خرید\s+(?!(?:سپر|دبیر)\s*$)\S.*$"),
)
async def group_purchase_message(
    message: Message,
    session: AsyncSession,
) -> None:
    if message.from_user is None or not message.text:
        return
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("فرمت خرید:\nخرید {اسم دبیر}\nخرید سپر {اسم سپر}")
        return
    name = parts[1].strip()
    is_shield = name.startswith("سپر ")
    if is_shield and name.startswith("سپر سپر "):
        name = name.removeprefix("سپر ").strip()
    if name.startswith("دبیر "):
        name = name.removeprefix("دبیر ").strip()
    try:
        user = await user_service.get_active_by_telegram_user_id(
            session, message.from_user.id
        )
        if not is_shield:
            teachers = matching_teachers(
                await teacher_service.public_teachers(session), name
            )
            if len(teachers) > 1:
                await message.answer(
                    "چند دبیر با این نام پیدا شد؛ اسم کامل دبیر را بنویسید: "
                    + "، ".join(teacher.name for teacher in teachers)
                )
                return
            if not teachers:
                await message.answer("دبیری با این نام پیدا نشد.")
                return
            teacher = teachers[0]
            await message.answer(
                purchase_banner(teacher),
                reply_markup=confirmation_keyboard(
                    action="teacher_buy", target_id=teacher.id, origin="buffet"
                ),
                reply_to_message_id=message.message_id,
                parse_mode=MARKDOWN_V2,
            )
            return

        shield_catalog = await shield_service.catalog(session, player_level=None)
        shield = next(
            (
                item
                for item in shield_catalog
                if item.name.casefold() == name.casefold()
            ),
            None,
        )
        if shield is not None:
            if user.level < shield.unlock_level:
                await message.answer(
                    f"سپر «{shield.name}» از سطح {shield.unlock_level} باز می‌شود."
                )
                return
            await message.answer(
                f"🛒 خرید سپر «{shield.name}»\n\n"
                f"قیمت: {shield.purchase_price} {_shield_currency(shield)}\n"
                f"مدت محافظت: {shield.duration_minutes} دقیقه\n"
                "اثر: جلوگیری کامل از حمله در مدت محافظت\n\n"
                "آیا خرید را تأیید می‌کنید؟",
                reply_markup=shield_purchase_confirmation(shield),
                reply_to_message_id=message.message_id,
            )
            return
        await message.answer("سپری با این نام پیدا نشد.")
    except TeacherSlotLocked:
        await message.answer(
            "ظرفیت دبیرهای شما پر است؛ یک دبیر را بفروشید یا سطح فرمانده را افزایش دهید."
        )
    except TeacherLimitReached:
        await message.answer(
            "به حداکثر تعداد دبیرهای قابل نگهداری رسیده‌اید؛ یک دبیر را بفروشید."
        )
    except TeacherAlreadyOwned:
        await message.answer("این دبیر را قبلاً خریده‌اید.")
    except TeacherLocked:
        await message.answer("این دبیر برای سطح فعلی شما باز نشده است.")
    except TeacherNotPurchasable:
        await message.answer("این دبیر فعلاً قابل خرید نیست.")
    except TeacherNotFound:
        await message.answer("این دبیر برای سطح شما پیدا نشد.")
    except InsufficientCoins:
        await message.answer("موجودی ارز کافی برای این خرید ندارید.")
    except SchoolError:
        await message.answer("این خرید در حال حاضر امکان‌پذیر نیست.")


def _resource_text(resources) -> str:
    return (
        f"{emoji('5823329527085931340', '🪙')} طلا: {escape(f'{resources.coin:,}')}\n"
        f"{emoji('5825753314570018832', '💎')} الماس: {escape(f'{resources.diamond:,}')}"
    )


def _conversion_banner(resources) -> str:
    return (
        f"{emoji('5451882707875276247', '🔄')} {bold('صرافی منابع')}\n\n"
        "موجودی فعلی:\n\n" + _resource_text(resources) + "\n\nیک تبدیل را انتخاب کنید:"
    )


def _buffet_menu_banner() -> str:
    return (
        f"{emoji('5823511728188563725', '🍽️')} {bold('بازار و بوفه')}\n\n"
        "« دبیر بخر، سپر بردار یا منابع رو تبدیل کن »\n\n"
        f"{emoji('5935912783261470019', '❓')} انتخاب با توئه\\."
    )


@router.message(F.text == BUFFET_LABEL)
async def buffet_handler(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    try:
        await user_service.get_active_by_telegram_user_id(session, message.from_user.id)
        await message.answer(
            section_entry_banner("بوفه"),
            reply_markup=buffet_menu_keyboard(),
            parse_mode=MARKDOWN_V2,
        )
        await message.answer(
            _buffet_menu_banner(),
            reply_markup=buffet_menu_keyboard(),
            parse_mode=MARKDOWN_V2,
        )
    except (UserInactiveError, SchoolUserNotFound):
        await message.answer("حساب شما فعال نیست.", reply_markup=main_menu_keyboard())


async def _buffet_menu_view(
    target: Message | CallbackQuery, session: AsyncSession
) -> None:
    text = _buffet_menu_banner()
    if isinstance(target, CallbackQuery) and target.message is not None:
        # Reply keyboards cannot be attached to editMessageText. Send a fresh
        # message so Telegram replaces the user's keyboard at the bottom.
        await target.message.answer(
            text, reply_markup=buffet_menu_keyboard(), parse_mode=MARKDOWN_V2
        )
    else:
        await target.answer(
            text, reply_markup=buffet_menu_keyboard(), parse_mode=MARKDOWN_V2
        )


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
            _conversion_banner(resources),
            reply_markup=buffet_keyboard(buffet_service.options()),
            parse_mode=MARKDOWN_V2,
        )
    except (UserInactiveError, SchoolUserNotFound):
        await message.answer("حساب شما فعال نیست.", reply_markup=main_menu_keyboard())


@router.message(F.text.regexp(r"^\s*(?:🛡\s*)?(?:فهرست\s+سپر\s*ها|خرید\s+سپر)\s*$"))
async def buffet_shields_message(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    if message.from_user is None:
        return
    if message.chat.type in {"group", "supergroup"}:
        await message.answer("فرمت خرید سپر: خرید سپر {اسم سپر}")
        return
    try:
        await state.clear()
        await _shields_view(message, session)
    except (UserInactiveError, SchoolUserNotFound):
        await message.answer("حساب شما فعال نیست.", reply_markup=main_menu_keyboard())


@router.message(F.text == "خرید سپر")
async def invalid_shield_purchase_message(
    message: Message,
) -> None:
    await message.answer("فرمت صحیح: خرید سپر {اسم سپر}")


@router.message(F.text.in_({"خرید دبیر", "👨‍🏫 خرید دبیر"}))
async def buffet_teachers_message(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    if message.from_user is None:
        return
    if message.chat.type in {"group", "supergroup"}:
        await message.answer("فرمت خرید دبیر: خرید {اسم دبیر}")
        return
    try:
        await state.clear()
        await user_service.get_active_by_telegram_user_id(session, message.from_user.id)
        await _teacher_shop_view(message, session)
    except (UserInactiveError, SchoolUserNotFound):
        await message.answer("حساب شما فعال نیست.", reply_markup=main_menu_keyboard())


async def _teacher_shop_view(
    target: Message | CallbackQuery, session: AsyncSession, page: int = 0
) -> None:
    if target.from_user is None:
        raise UserInactiveError
    user = await user_service.get_active_by_telegram_user_id(
        session, target.from_user.id
    )
    catalog = await teacher_service.public_teachers(session)
    text = "👨‍🏫 بازار نقل‌وانتقال دبیرها\n\nعضو بعدی تیم رویایی‌ات رو انتخاب کن 👇"
    markup = teacher_catalog_page_keyboard(
        catalog,
        player_level=user.level,
        page=page,
        back_action="back_buffet",
        origin="buffet",
    )
    if isinstance(target, CallbackQuery) and target.message is not None:
        await safe_edit_text(target.message, text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(F.text.in_({"منوی اصلی", "لغو", "بازگشت به منو اصلی", "❌ لغو"}))
async def buffet_back_to_main(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("به منوی اصلی برگشتید.", reply_markup=main_menu_keyboard())


async def _conversion_view(target: CallbackQuery, session: AsyncSession) -> None:
    if target.from_user is None or not isinstance(target.message, Message):
        raise UserInactiveError
    user = await user_service.get_active_by_telegram_user_id(
        session, target.from_user.id
    )
    resources = await buffet_service.resources(session, user.id)
    if resources is None:
        raise UserInactiveError
    text = _conversion_banner(resources)
    await safe_edit_text(
        target.message,
        text,
        reply_markup=buffet_keyboard(buffet_service.options()),
        parse_mode=MARKDOWN_V2,
    )


def _shield_catalog_banner(player_level: int, owned: list, catalog: list) -> str:
    shield_icon = emoji("5915888842568638290", "🤩")
    time_icon = emoji("6039539366177541657", "⏳")
    level_icon = emoji("5825727141039317043", "🎖️")
    lines = [
        f"{shield_icon} {bold('زرادخانه سپرها')} {shield_icon}",
        f"{level_icon} سطح فرمانده: {bold(player_level)}",
    ]
    if owned:
        for item in owned:
            remaining = max(
                0, int((item.active_until - datetime.now(UTC)).total_seconds())
            )
            minutes = (remaining + 59) // 60
            lines.append(
                f"● وضعیت دفاعی شما: {bold(item.shield.name)}\n"
                f"{time_icon} زمان باقی‌مانده: {escape(minutes)} دقیقه"
            )
    else:
        lines.append("● وضعیت دفاعی شما :  « هنوز سپر فعالی نداری »")
    lines.append("────────────────────")
    lines.append(
        f"{emoji('5825898080737697438', '📜')} {bold('لیست سپرهای قابل خرید:')}"
    )
    header_count = len(lines)
    if not catalog:
        lines.append("فعلاً سپری تعریف نشده است\\.")
    else:
        for shield in catalog:
            currency_icon = emoji(
                "5825753314570018832"
                if shield.purchase_resource is ResourceType.DIAMOND
                else "5825699971076202989",
                "💎" if shield.purchase_resource is ResourceType.DIAMOND else "🪙",
            )
            description = " ".join((shield.description or "").split())
            daily_limit = SHIELD_DAILY_LIMITS.get(shield.name)
            limit_line = (
                f"\n\n{emoji('5427240268589968037', '⛔️')} در طول روز فقط "
                f"{escape(daily_limit)} بار میتونید از این سپر استفاده کنید\\."
                if daily_limit
                else ""
            )
            lines.append(
                f"{emoji(SHIELD_ICONS.get(shield.name, '5825861861278490879'), SHIELD_FALLBACKS.get(shield.name, '🛡️'))} {bold(shield.name)}\n\n"
                f"{currency_icon} قیمت: {bold(shield.purchase_price)} "
                f"{escape(_shield_currency(shield))}\n"
                f"{time_icon} مدت محافظت: {escape(shield.duration_minutes)} دقیقه\n"
                f"{emoji('5825699618888884083', '👑')} سطح بازشدن: {escape(shield.unlock_level)}\n"
                f"{bold('اثر:')} جلوگیری کامل از حمله"
                + (f"\n{escape(description)}" if description else "")
                + limit_line
            )
    heading = "\n\n".join(lines[:header_count])
    shields = lines[header_count:]
    body = heading + (
        "\n\n" + "\n\n┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n".join(shields) if shields else ""
    )
    return body + (
        "\n\n────────────────────\n"
        f"{emoji('5823388325188214894', '🚫')} "
        "توجه داشته باشید که در صورت داشتن سپر و انجام حملات، از تایم سپرتون کم میشه "
        f"{emoji('5823388325188214894', '🚫')}"
    )


async def _shields_view(target: Message | CallbackQuery, session: AsyncSession) -> None:
    if target.from_user is None:
        raise UserInactiveError
    user = await user_service.get_active_by_telegram_user_id(
        session, target.from_user.id
    )
    owned = await shield_service.list_owned(session, user.id)
    catalog = await shield_service.catalog(session, player_level=None)
    text = _shield_catalog_banner(user.level, owned, catalog)
    reply_markup = (
        shield_catalog_keyboard(catalog, owned, player_level=user.level)
        if catalog
        else shield_inventory_keyboard(owned)
    )
    if isinstance(target, CallbackQuery) and target.message is not None:
        await safe_edit_text(
            target.message, text, reply_markup=reply_markup, parse_mode=MARKDOWN_V2
        )
    else:
        await target.answer(text, reply_markup=reply_markup, parse_mode=MARKDOWN_V2)


@router.callback_query(BuffetCallback.filter())
async def buffet_callback(
    callback: CallbackQuery,
    callback_data: BuffetCallback,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
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
            f"چه مقدار {_resource_display(source)} می‌خواهید تبدیل کنید؟\n"
            f"هر {option.source_amount} {_resource_display(source)} = "
            f"{option.target_amount} {_resource_display(target)}\n"
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
    if callback.from_user is None or not isinstance(callback.message, Message):
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
    if callback.from_user is None or not isinstance(callback.message, Message):
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
            await callback.answer(
                "اطلاعات خرید نمایش داده شد؛ تأیید کنید.",
            )
            await callback.message.answer(
                f"🛒 خرید سپر «{shield.name}»\n\n"
                f"قیمت: {shield.purchase_price} {_shield_currency(shield)}\n"
                f"مدت محافظت: {shield.duration_minutes} دقیقه\n"
                "اثر: جلوگیری کامل از حمله در مدت محافظت\n\n"
                "آیا خرید را تأیید می‌کنید؟",
                reply_markup=shield_purchase_confirmation(shield),
            )
            return
        await callback.answer()
    except InsufficientCoins:
        await callback.answer("موجودی ارز کافی ندارید.", show_alert=True)
    except ShieldLocked:
        await callback.answer("این سپر برای سطح شما باز نشده است.", show_alert=True)
    except ShieldAlreadyActive:
        await callback.answer(
            "در حال حاضر یک سپر فعال دارید؛ پس از انقضای آن سپر دیگری بخرید.",
            show_alert=True,
        )
        await _delete_group_purchase_prompt(callback)
    except (
        ShieldNotFound,
        ShieldNotPurchasable,
        UserInactiveError,
        SchoolUserNotFound,
    ):
        await callback.answer("این سپر در دسترس نیست.", show_alert=True)


@router.callback_query(ShieldPurchaseCallback.filter())
async def shield_purchase_callback(
    callback: CallbackQuery,
    callback_data: ShieldPurchaseCallback,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    source_message = group_user_request(callback.message)
    if (
        source_message is not None
        and source_message.from_user is not None
        and source_message.from_user.id != callback.from_user.id
    ):
        await callback.answer(
            "فقط کاربری که درخواست خرید داده می‌تواند آن را تأیید کند.",
            show_alert=True,
        )
        return
    try:
        user = await user_service.get_active_by_telegram_user_id(
            session, callback.from_user.id
        )
        if callback_data.decision == "cancel":
            with suppress(TelegramAPIError):
                await callback.message.delete()
            await callback.answer("خرید لغو شد.")
            return
        shield = await shield_service.get_shield(session, callback_data.shield_id)
        if shield is None:
            raise ShieldNotFound
        purchase = await shield_service.buy(session, user.id, shield.id)
        # The purchase is durable before Telegram I/O starts. A slow or
        # deleted group message must not hold the database connection.
        await session.commit()
        with suppress(TelegramAPIError):
            await callback.message.delete()
        await callback.message.answer(
            f"✅ سپر «{purchase.shield.name}» خریداری شد.\n"
            f"🛡 مدت محافظت: {purchase.shield.duration_minutes} دقیقه\n"
            "سپر شما همین حالا فعال شد.",
            reply_to_message_id=(
                source_message.message_id if source_message is not None else None
            ),
            disable_group_reply=source_message is None,
        )
        await callback.answer("خرید با موفقیت انجام شد.")
    except InsufficientCoins as error:
        await session.rollback()
        reason = (
            "الماس کافی برای خرید این سپر ندارید."
            if isinstance(error, InsufficientDiamonds)
            else "طلا کافی برای خرید این سپر ندارید."
        )
        await _answer_shield_purchase_error(callback, source_message, reason)
    except ShieldAlreadyActive:
        await session.rollback()
        await _answer_shield_purchase_error(
            callback,
            source_message,
            "همین حالا یک سپر فعال دارید؛ پس از انقضای آن سپر دیگری بخرید.",
        )
    except ShieldDailyLimitReached:
        await session.rollback()
        await _answer_shield_purchase_error(
            callback, source_message, "سقف استفادهٔ روزانه از این سپر پر شده است."
        )
    except (
        ShieldLocked,
        ShieldNotFound,
        ShieldNotPurchasable,
        ResourceNotFound,
        UserInactiveError,
        SchoolUserNotFound,
    ):
        await session.rollback()
        await _answer_shield_purchase_error(
            callback, source_message, "این سپر دیگر قابل خرید نیست."
        )


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
        f"مصرف‌شده: {amount} {_resource_display(source)}\n"
        f"دریافت‌شده: {result.packages * result.conversion.target_amount} {_resource_display(target)}\n\n"
        "موجودی جدید:\n" + _resource_text(resources),
        reply_markup=main_menu_keyboard(),
    )
