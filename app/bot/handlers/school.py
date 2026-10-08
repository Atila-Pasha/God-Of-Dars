from contextlib import suppress
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.banners import (
    FORT,
    LEVEL,
    MARKDOWN_V2,
    QUESTION,
    SCHOOL,
    UNLOCK,
    bold,
    emoji,
    escape,
    purchase_banner,
    rich_plain,
    section_entry_banner,
    teacher_icon,
)
from app.bot.callbacks import (
    CastleCallback,
    ConfirmationCallback,
    HospitalCallback,
    SchoolCallback,
    TeacherCallback,
)
from app.bot.keyboards.main_menu import (
    MENU_SECTION_BY_LABEL,
    main_menu_keyboard,
    section_back_keyboard,
)
from app.bot.keyboards.school import (
    castle_keyboard,
    confirmation_keyboard,
    hospital_keyboard,
    school_keyboard,
    teacher_catalog_keyboard,
    teacher_catalog_page_keyboard,
    teacher_detail_keyboard,
    teachers_keyboard,
)
from app.bot.progress import premium_progress_bar
from app.bot.utils.telegram import group_user_request, safe_edit_text
from app.core.enums import TeacherStatus
from app.core.game_logic import GameConfigurationError
from app.models.user_teacher import UserTeacher
from app.services.castle_service import CastleService
from app.services.recovery_service import HospitalService
from app.services.school_errors import (
    AttackInProgress,
    CastleNeedsRepair,
    HospitalFull,
    HospitalUpgradeUnavailable,
    InsufficientCoins,
    InsufficientDiamonds,
    SchoolError,
    TeacherAlreadyOwned,
    TeacherLimitReached,
    TeacherLocked,
    TeacherNotFound,
    TeacherNotPurchasable,
    TeacherSlotLocked,
)
from app.services.teacher_service import TeacherService
from app.services.user_service import UserInactiveError, UserService

router = Router(name="school")
user_service = UserService()
castle_service = CastleService()
teacher_service = TeacherService()
hospital_service = HospitalService()

SCHOOL_LABEL = next(
    label for label, section in MENU_SECTION_BY_LABEL.items() if section == "school"
)
STATUS_LABELS = {
    TeacherStatus.ACTIVE: "فعال",
    TeacherStatus.INJURED: "مصدوم",
    TeacherStatus.DISABLED: "غیرفعال",
    TeacherStatus.RECOVERING: "در حال درمان",
}
STATUS_ICONS = {
    TeacherStatus.ACTIVE: "🟢",
    TeacherStatus.INJURED: "🟠",
    TeacherStatus.DISABLED: "🔴",
    TeacherStatus.RECOVERING: "🔵",
}


def _number(value: int) -> str:
    return str(value)


def _duration_text(minutes: int | None) -> str:
    if minutes is None:
        return "تنظیم نشده"
    hours, remaining = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{_number(hours)} ساعت")
    if remaining or not parts:
        parts.append(f"{_number(remaining)} دقیقه")
    return " و ".join(parts)


def _progress_bar(value: int, maximum: int, *, width: int = 8) -> str:
    return premium_progress_bar(value, maximum, width=width)


def _progress_percent(value: int, maximum: int) -> str:
    if maximum <= 0:
        return "—"
    return _number(round(max(0, min(value, maximum)) / maximum * 100)) + "%"


def _teacher_hp_banner(current_hp: int, max_hp: int) -> str:
    """Keep the custom-emoji chart on its own line in right-to-left messages."""
    amount = f"\u2066{_number(current_hp)} / {_number(max_hp)} HP\u2069"
    return (
        f"{emoji('5213455977919039650', '❤️')} جان دبیر: {bold(amount)} "
        f"{escape(f'({_progress_percent(current_hp, max_hp)})')}\n"
        f"{_progress_bar(current_hp, max_hp)}"
    )


def _teacher_purchase_error(error: Exception) -> str:
    if isinstance(error, (TeacherSlotLocked, TeacherLimitReached)):
        return (
            "ظرفیت دبیرهای شما پر است؛ یک دبیر را بفروشید "
            "یا سطح فرمانده را افزایش دهید."
        )
    if isinstance(error, TeacherAlreadyOwned):
        return "این دبیر را قبلاً خریده‌اید."
    if isinstance(error, TeacherLocked):
        return "این دبیر برای سطح فعلی شما باز نشده است."
    if isinstance(error, TeacherNotFound):
        return "این دبیر دیگر در فهرست خرید نیست."
    if isinstance(error, TeacherNotPurchasable):
        return "این دبیر فعلاً قابل خرید نیست."
    if isinstance(error, InsufficientDiamonds):
        return "الماس کافی برای خرید این دبیر ندارید."
    if isinstance(error, InsufficientCoins):
        return "سکه کافی برای خرید این دبیر ندارید."
    return "خرید دبیر در حال حاضر امکان‌پذیر نیست."


async def _delete_group_purchase_prompt(callback: CallbackQuery) -> None:
    message = callback.message
    if not isinstance(message, Message) or message.chat.type not in {
        "group",
        "supergroup",
    }:
        return
    with suppress(TelegramAPIError):
        await message.delete()


async def _user(session: AsyncSession, telegram_user_id: int):
    return await user_service.get_active_by_telegram_user_id(session, telegram_user_id)


def _status(teacher: UserTeacher) -> str:
    if HospitalService.ready_for_discharge(teacher):
        return "درمان کامل شده؛ در انتظار ترخیص"
    return STATUS_LABELS.get(teacher.status, teacher.status.value)


def _status_icon(teacher: UserTeacher) -> str:
    return STATUS_ICONS.get(teacher.status, "⚪")


def _recovery_text(teacher: UserTeacher) -> str:
    if HospitalService.ready_for_discharge(teacher):
        return "درمان دبیر کامل شده ولی ترخیص نشده؛ به بیمارستان برو و ترخیصش کن."
    recovery = next(
        (item for item in teacher.recoveries if item.completed_at is None), None
    )
    if recovery is None:
        return "زمان درمان: تنظیم نشده"
    end_at = recovery.recovery_end_at
    if end_at.tzinfo is None:
        end_at = end_at.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return f"پایان درمان: {end_at.astimezone().strftime('%Y-%m-%d %H:%M')}"


async def _send_or_edit(
    target: Message | CallbackQuery,
    text: str,
    *,
    reply_markup,
    parse_mode: str | None = None,
) -> None:
    formatting = {"parse_mode": parse_mode} if parse_mode else {}
    if isinstance(target, CallbackQuery):
        if target.message is None:
            return
        try:
            await safe_edit_text(
                target.message,
                text,
                reply_markup=reply_markup,
                **formatting,
            )
        except TelegramAPIError:
            await target.message.answer(
                text,
                reply_markup=reply_markup,
                **formatting,
            )
        return
    await target.answer(text, reply_markup=reply_markup, **formatting)


async def _school_view(
    target: Message | CallbackQuery,
    session: AsyncSession,
) -> None:
    if target.from_user is None:
        raise UserInactiveError
    user = await _user(session, target.from_user.id)
    castle = await castle_service.snapshot(session, user.id)
    capacity = await teacher_service.capacity(session, user.id)
    from app.bot.handlers.profile import _level_unlocks

    next_level = user.level + 1
    if user.level < castle_service.config.level_progression.max_level:
        unlocks = await _level_unlocks(session, next_level)
        unlocks = "\n".join(
            f"▫️ {escape(line.removeprefix('•').strip())}"
            for line in unlocks.splitlines()
        )
    else:
        unlocks = "▫️ به بالاترین سطح فرماندهی رسیده‌ای\\."
    unlock_heading = (
        f"مسیر پیشرفت فرمانده | سطح {next_level}:"
        if user.level < castle_service.config.level_progression.max_level
        else "مسیر پیشرفت فرمانده"
    )
    progress = _progress_bar(capacity.owned, capacity.available)
    percentage = _progress_percent(capacity.owned, capacity.available)
    text = (
        f"{SCHOOL} {bold('ستاد فرماندهی مدرسه')} {QUESTION}\n"
        "─────────────────────\n"
        f"{LEVEL} سطح فرمانده: {escape(_number(user.level))}\n\n"
        f"{UNLOCK} {bold(unlock_heading)}\n"
        f"{unlocks}\n\n"
        f"{FORT} سطح دژ: {escape(_number(castle.level))}\n"
        f"{emoji('5915633360734002967', '🛡️')} قدرت دفاعی: {escape(_number(castle.strength + castle.defense_power))}\n\n"
        f"● {bold('ظرفیت تیم دبیرها')}\n"
        f"{progress}  {escape(_number(capacity.owned))} / "
        f"{escape(_number(capacity.available))} "
        f"{escape(f'({percentage})')}"
    )
    if isinstance(target, Message):
        await target.answer(
            section_entry_banner("مدرسه من"),
            reply_markup=section_back_keyboard(),
            parse_mode=MARKDOWN_V2,
        )
    await _send_or_edit(
        target, text, reply_markup=school_keyboard(), parse_mode=MARKDOWN_V2
    )


async def _castle_view(
    target: CallbackQuery,
    session: AsyncSession,
) -> None:
    user = await _user(session, target.from_user.id)
    castle = await castle_service.snapshot(session, user.id)
    castle_model = await castle_service.repository.get_by_user(
        session, user.id, for_update=False
    )
    can_repair = (
        castle_model is not None
        and castle_service.repair_quote(castle_model).missing_strength > 0
    )
    text = (
        f"{FORT} {bold('دژ مدرسه | خط مقدم دفاع')}\n\n"
        f"● سطح دژ: {escape(castle.level)}\n\n"
        f"{emoji('5213455977919039650', '❤️')} سلامت دژ: « {escape(castle.strength)} / "
        f"{escape(castle_service.config.castle_max_strength(castle.level))} »\n"
        f"{emoji('5917841858687411504', '🛡️')} قدرت سیستم دفاعی: « {escape(castle.defense_power)} »\n\n"
        f"{emoji('5915888842568638290', '🛡️')} توان دفاعی نهایی: « {escape(castle.strength + castle.defense_power)} »"
        + (
            "\n\nدژ آسیب‌دیده است؛ برای ارتقا ابتدا آن را تعمیر کن\\."
            if can_repair
            else ""
        )
    )
    await _send_or_edit(
        target,
        text,
        reply_markup=castle_keyboard(
            castle_service.can_upgrade_level(castle.level),
            can_repair=can_repair,
        ),
        parse_mode=MARKDOWN_V2,
    )


async def _teachers_view(
    target: Message | CallbackQuery,
    session: AsyncSession,
    *,
    from_buffet: bool = False,
) -> None:
    if target.from_user is None:
        raise UserInactiveError
    user = await _user(session, target.from_user.id)
    capacity = await teacher_service.capacity(session, user.id)
    teachers = await teacher_service.owned(session, user.id)
    catalog = await teacher_service.catalog(session, user.id)
    text_lines = [
        f"{emoji('5825625629487276345', '👨‍🏫')} {bold('تیم دبیرهای من')}",
        "",
        f"{LEVEL} سطح شما: {escape(_number(user.level))}",
        "",
        f"{emoji('5825667690102006523', '📊')} ظرفیت استفاده‌شده:",
        (
            f"{_progress_bar(capacity.owned, capacity.available)}  "
            f"{escape(_number(capacity.owned))} / {escape(_number(capacity.available))} "
            f"{escape(f'({_progress_percent(capacity.owned, capacity.available)})')}"
        ),
        "",
    ]
    if teachers:
        text_lines.append(f"{emoji('5866218662481892680', '👥')} فهرست دبیرها")
    else:
        text_lines.append(rich_plain("🌱 هنوز دبیری به مدرسه‌تان اضافه نشده است."))
    await _send_or_edit(
        target,
        "\n".join(text_lines),
        reply_markup=teachers_keyboard(
            teachers,
            catalog,
            can_buy=from_buffet
            and (
                capacity.owned < capacity.available
                and (capacity.maximum is None or capacity.owned < capacity.maximum)
                and any(teacher.unlock_level <= user.level for teacher in catalog)
            ),
            back_action="back_buffet" if from_buffet else "back_school",
        ),
        parse_mode=MARKDOWN_V2,
    )


async def _teacher_view(
    target: CallbackQuery,
    session: AsyncSession,
    user_teacher_id: int,
) -> None:
    user = await _user(session, target.from_user.id)
    teacher = await teacher_service.get_owned(session, user.id, user_teacher_id)
    damage = "تنظیم نشده"
    with suppress(SchoolError):
        damage = str(teacher_service.damage(teacher))
    damage_text = damage if damage == "تنظیم نشده" else _number(int(damage))
    details = f"🎖 سطح: {_number(teacher.level)}\n⚔️ قدرت ضربه: {damage_text}\n"
    after_bar = (
        f"📌 وضعیت: {_status(teacher)}\n"
        f"✨ توانایی: {teacher.teacher.ability_text or 'تنظیم نشده'}\n\n"
        f"⏳ {_recovery_text(teacher)}"
    )
    text = (
        f"{teacher_icon(teacher.teacher.emoji)}    "
        f"{bold(f'پروندهٔ عملیاتی | {teacher.teacher.name}')}\n\n"
        f"{rich_plain(details)}"
        f"{_teacher_hp_banner(teacher.current_hp, teacher.teacher.max_hp)}\n\n"
        f"{rich_plain(after_bar)}"
    )
    await _send_or_edit(
        target,
        text,
        reply_markup=teacher_detail_keyboard(
            teacher,
            can_upgrade=teacher_service.can_upgrade(teacher),
            can_sell=teacher_service.can_sell(teacher),
            can_activate=hospital_service.can_activate(),
        ),
        parse_mode=MARKDOWN_V2,
    )


async def _hospital_view(
    target: CallbackQuery,
    session: AsyncSession,
) -> None:
    user = await _user(session, target.from_user.id)
    patients = await hospital_service.patients(session, user.id)
    hospital = await hospital_service.snapshot(session, user.id)
    lines = [
        f"{emoji('5825570280243732195', '🏥')} {bold('بیمارستان مدرسه')}",
        "",
        f"{emoji('5825727141039317043', '🎖')} {escape('سطح بیمارستان:')} {escape(_number(hospital.level))}",
        f"{emoji('5275983061001977055', '🛏')} {escape('تخت‌های اشغال‌شده:')} {escape(_number(hospital.occupied))} {escape('/')} {escape(_number(hospital.capacity))}",
        f"{emoji('6039539366177541657', '⏳')} {bold('سرعت درمان بیمارستان')}",
        f"> {bold(f'{hospital.heal_hp_per_hour} HP در ساعت')}",
        "",
        escape("زمان بستری جدید بر اساس جان ازدست‌رفتهٔ هر دبیر حساب می‌شود."),
        "",
    ]
    if not patients:
        lines.append(escape("در حال حاضر دبیر مصدوم یا غیرفعالی ندارید."))
    else:
        for teacher in patients:
            missing_hp = max(0, teacher.teacher.max_hp - teacher.current_hp)
            lines.extend(
                [
                    f"{rich_plain(_status_icon(teacher))} {escape(teacher.teacher.name)}  •  {escape(_status(teacher))}",
                    _teacher_hp_banner(teacher.current_hp, teacher.teacher.max_hp),
                    *(
                        [
                            f"{emoji('5825570280243732195', '🩸')} {escape('آسیب:')} {escape(_number(missing_hp))} {escape('HP')}  •  {escape('زمان بستری:')} {escape(_duration_text(hospital_service.config.hospital_recovery_minutes(hospital.level, missing_hp)))}"
                        ]
                        if missing_hp
                        and teacher.status
                        in {TeacherStatus.INJURED, TeacherStatus.ACTIVE}
                        else []
                    ),
                    *(
                        [
                            f"{emoji('6039539366177541657', '⏳')} {escape(_recovery_text(teacher))}"
                        ]
                        if teacher.status is TeacherStatus.RECOVERING
                        else []
                    ),
                    "",
                ]
            )
    await _send_or_edit(
        target,
        "\n".join(lines).rstrip(),
        reply_markup=hospital_keyboard(
            patients,
            can_activate=hospital_service.can_activate(),
            can_recover=hospital_service.can_begin_recovery(),
            instant_recovery_cost=hospital_service.instant_recovery_cost(),
            can_upgrade=hospital.upgrade_cost is not None,
        ),
        parse_mode=MARKDOWN_V2,
    )


@router.message(F.text == SCHOOL_LABEL)
async def school_handler(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    try:
        await _school_view(message, session)
    except UserInactiveError:
        await message.answer("حساب شما مسدود شده است.")
    except SchoolError:
        await message.answer("اطلاعات مدرسه در دسترس نیست. ابتدا /start را بزنید.")


@router.message(F.text == "بازگشت به منو اصلی")
async def school_back_message(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "به منوی اصلی برگشتید.",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(SchoolCallback.filter())
async def school_callback_handler(
    callback: CallbackQuery,
    callback_data: SchoolCallback,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    try:
        if callback_data.action == "castle":
            await _castle_view(callback, session)
        elif callback_data.action == "teachers":
            await _teachers_view(callback, session)
        elif callback_data.action == "hospital":
            await _hospital_view(callback, session)
        elif callback_data.action == "back":
            if callback.message is None:
                await callback.answer()
                return
            await callback.message.answer(
                "به منوی اصلی برگشتید.",
                reply_markup=main_menu_keyboard(),
            )
        await callback.answer()
    except (SchoolError, UserInactiveError):
        await callback.answer("اطلاعات مدرسه در دسترس نیست.", show_alert=True)


@router.callback_query(CastleCallback.filter())
async def castle_callback_handler(
    callback: CallbackQuery,
    callback_data: CastleCallback,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    try:
        notice = None
        if callback_data.action == "back":
            await _school_view(callback, session)
        elif callback_data.action == "upgrade":
            user = await _user(session, callback.from_user.id)
            castle = await castle_service.snapshot(session, user.id)
            if castle.strength < castle_service.config.castle_max_strength(
                castle.level
            ):
                await callback.answer(
                    "اول دژ را تعمیر کن، بعد ارتقا بده.", show_alert=True
                )
                return
            upgrade = castle_service.config.castle_upgrade(castle.level)
            banana_reward = castle_service.config.upgrade_banana_reward(
                upgrade.diamond_cost
            )
            await _send_or_edit(
                callback,
                f"{FORT} {bold('ارتقای دژ')} {emoji('5866060208253441223', '⬆️')}\n"
                "─────────────────────\n"
                f"سطح: {escape(castle.level)} {emoji('5235470399730361615', '➡️')} {escape(castle.level + 1)}\n\n"
                f"{emoji('5866369239740320716', '💎')} هزینه ارتقا: {escape(upgrade.diamond_cost)} الماس {emoji('5825753314570018832', '💎')}\n"
                "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
                f"{emoji('5866218662481892680', '📈')} تغییرات بعد از ارتقا:\n\n"
                f"{emoji('5213455977919039650', '❤️')} استحکام: {escape(castle.strength)} {emoji('5235470399730361615', '➡️')} "
                f"{escape(castle.strength + upgrade.strength_delta)} "
                f"{escape(f'(+{upgrade.strength_delta})')}\n\n"
                f"{emoji('5917841858687411504', '🛡️')} قدرت دفاع: {escape(castle.defense_power)} {emoji('5235470399730361615', '➡️')} "
                f"{escape(castle.defense_power + upgrade.defense_delta)} "
                f"{escape(f'(+{upgrade.defense_delta})')}\n\n"
                f"{emoji('5823415254633160881', '🍌')} پاداش ارتقا: {escape(banana_reward)} موز {emoji('5902520589356113908', '🍌')}\n\n"
                f"{emoji('5935912783261470019', '❓')} آیا می‌خواهی ارتقای دژ را انجام بدهم؟",
                reply_markup=confirmation_keyboard(
                    action="castle_upgrade", target_id=0
                ),
                parse_mode=MARKDOWN_V2,
            )
            await callback.answer()
            return
        elif callback_data.action == "repair":
            user = await _user(session, callback.from_user.id)
            castle_model = await castle_service.repository.get_by_user(
                session, user.id, for_update=False
            )
            if castle_model is None:
                raise SchoolError
            quote = castle_service.repair_quote(castle_model)
            if quote.missing_strength == 0:
                await callback.answer("دژ نیازی به تعمیر ندارد.", show_alert=True)
                return
            await _send_or_edit(
                callback,
                f"🔧 تعمیر دژ\n\n"
                f"مقدار آسیب: {_number(quote.missing_strength)} واحد\n"
                f"هزینه تعمیر: {_number(quote.diamond_cost)} الماس\n"
                "آیا می‌خواهی دژ را تعمیر کنم؟",
                reply_markup=confirmation_keyboard(action="castle_repair", target_id=0),
            )
            await callback.answer()
            return
        else:
            await _castle_view(callback, session)
        await callback.answer(notice)
    except InsufficientDiamonds:
        await callback.answer("الماس کافی برای ارتقا ندارید.", show_alert=True)
    except (SchoolError, GameConfigurationError):
        await callback.answer("ارتقای دژ در حال حاضر امکان‌پذیر نیست.", show_alert=True)


@router.callback_query(TeacherCallback.filter())
async def teacher_callback_handler(
    callback: CallbackQuery,
    callback_data: TeacherCallback,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    try:
        user = await _user(session, callback.from_user.id)
        if callback_data.action == "view":
            await _teacher_view(callback, session, callback_data.teacher_id)
            await callback.answer()
        elif callback_data.action == "back_school":
            await _school_view(callback, session)
            await callback.answer()
        elif callback_data.action == "back_teachers":
            await _teachers_view(callback, session)
            await callback.answer()
        elif callback_data.action == "back_buffet":
            from app.bot.handlers.buffet import _buffet_menu_view

            await _buffet_menu_view(callback, session)
            await callback.answer()
        elif callback_data.action == "buy" and callback_data.teacher_id == 0:
            catalog = await teacher_service.catalog(session, user.id)
            await _send_or_edit(
                callback,
                "🛒 خرید دبیر\n\nدبیر موردنظر را انتخاب کنید:",
                reply_markup=teacher_catalog_keyboard(
                    catalog,
                    player_level=user.level,
                    back_action="back_buffet",
                    origin="buffet",
                ),
            )
            await callback.answer()
        elif callback_data.action == "page":
            catalog = await teacher_service.catalog(session, user.id)
            await _send_or_edit(
                callback,
                "🛒 خرید دبیر\n\nدبیر موردنظر را انتخاب کنید:",
                reply_markup=teacher_catalog_page_keyboard(
                    catalog,
                    player_level=user.level,
                    page=callback_data.page,
                    back_action="back_teachers",
                    origin=callback_data.origin,
                ),
            )
            await callback.answer()
        elif callback_data.action == "buy":
            teacher = await teacher_service.catalog_teacher(
                session, callback_data.teacher_id
            )
            if callback_data.origin == "buffet":
                await _send_or_edit(
                    callback,
                    purchase_banner(teacher),
                    reply_markup=confirmation_keyboard(
                        action="teacher_buy", target_id=teacher.id, origin="buffet"
                    ),
                    parse_mode=MARKDOWN_V2,
                )
                await callback.answer()
                return
            await _send_or_edit(
                callback,
                purchase_banner(teacher),
                reply_markup=confirmation_keyboard(
                    action="teacher_buy",
                    target_id=teacher.id,
                    origin=callback_data.origin,
                ),
                parse_mode=MARKDOWN_V2,
            )
            await callback.answer()
        elif callback_data.action == "upgrade":
            owned = await teacher_service.get_owned(
                session, user.id, callback_data.teacher_id
            )
            upgrade_cost = teacher_service.upgrade_cost(owned)
            current_damage = teacher_service.damage(owned)
            next_damage = teacher_service.config.teacher_damage(
                owned.teacher.id,
                owned.level + 1,
                owned.teacher.damage,
            )
            banana_reward = teacher_service.config.upgrade_banana_reward(upgrade_cost)
            await _send_or_edit(
                callback,
                f"⬆️ ارتقای دبیر {owned.teacher.name}\n\n"
                f"ارتقا از سطح {_number(owned.level)} به {_number(owned.level + 1)}\n"
                f"هزینه: {_number(upgrade_cost)} الماس\n"
                "\n📈 بعد از ارتقا:\n"
                f"⚔️ قدرت دبیر: {_number(current_damage)} → "
                f"{_number(next_damage)} (+{_number(next_damage - current_damage)})\n"
                f"🍌 پاداش ارتقا: {_number(banana_reward)} موز\n\n"
                "آیا می‌خواهی دبیر را ارتقا بدهم؟",
                reply_markup=confirmation_keyboard(
                    action="teacher_upgrade", target_id=owned.id
                ),
            )
            await callback.answer()
        elif callback_data.action == "sell":
            owned = await teacher_service.get_owned(
                session, user.id, callback_data.teacher_id
            )
            if owned.current_hp < owned.teacher.max_hp:
                await callback.answer(
                    "جان دبیرت باید با درمان کامل بشه.",
                    show_alert=True,
                )
                return
            price = teacher_service.sell_price(owned)
            await _send_or_edit(
                callback,
                f"💰 فروش دبیر {owned.teacher.name}\n\n"
                f"مبلغ دریافتی: {_number(price)} سکه\n"
                "آیا می‌خواهی این دبیر را بفروشی؟",
                reply_markup=confirmation_keyboard(
                    action="teacher_sell", target_id=owned.id
                ),
            )
            await callback.answer()
        elif callback_data.action == "activate":
            cost = hospital_service.instant_recovery_cost()
            if cost is None:
                raise SchoolError
            owned = await teacher_service.get_owned(
                session, user.id, callback_data.teacher_id
            )
            await _send_or_edit(
                callback,
                f"⚡ فعال‌سازی دبیر {owned.teacher.name}\n\n"
                f"هزینه: {_number(cost)} الماس\n"
                "آیا می‌خواهی دبیر را فعال کنم؟",
                reply_markup=confirmation_keyboard(
                    action="teacher_activate", target_id=owned.id
                ),
            )
            await callback.answer()
        elif callback_data.action == "send_to_hospital":
            await hospital_service.send_to_hospital(
                session, user.id, callback_data.teacher_id
            )
            await _teacher_view(callback, session, callback_data.teacher_id)
            await callback.answer("دبیر به بیمارستان فرستاده شد.")
    except HospitalFull:
        await callback.answer(
            "تخت‌های بیمارستان پر هستند. دبیر درمان‌شده را ترخیص کن یا بیمارستان را ارتقا بده.",
            show_alert=True,
        )
    except InsufficientDiamonds:
        await callback.answer("الماس کافی برای ارتقا ندارید.", show_alert=True)
    except SchoolError:
        await callback.answer("این عملیات در حال حاضر امکان‌پذیر نیست.", show_alert=True)


@router.callback_query(ConfirmationCallback.filter())
async def confirmation_callback_handler(
    callback: CallbackQuery,
    callback_data: ConfirmationCallback,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    purchase_source = (
        group_user_request(callback.message)
        if callback_data.action == "teacher_buy"
        and isinstance(callback.message, Message)
        else None
    )
    if (
        purchase_source is not None
        and purchase_source.from_user is not None
        and purchase_source.from_user.id != callback.from_user.id
    ):
        await callback.answer(
            "فقط کاربری که درخواست خرید داده می‌تواند آن را تأیید کند.",
            show_alert=True,
        )
        return
    try:
        user = await _user(session, callback.from_user.id)
        if callback_data.decision == "cancel":
            if (
                callback_data.action == "teacher_buy"
                and isinstance(callback.message, Message)
                and callback.message.chat.type in {"group", "supergroup"}
            ):
                with suppress(TelegramAPIError):
                    await callback.message.delete()
                await callback.answer("خرید دبیر لغو شد.")
                return
            if callback_data.action == "castle_upgrade":
                await _castle_view(callback, session)
            elif callback_data.action in {
                "hospital_instant_recover",
                "hospital_upgrade",
            }:
                await _hospital_view(callback, session)
            else:
                if callback_data.origin == "buffet":
                    from app.bot.handlers.buffet import _teacher_shop_view

                    await _teacher_shop_view(callback, session)
                else:
                    await _teachers_view(callback, session)
            await callback.answer("عملیات لغو شد.")
            return

        if callback_data.action == "castle_upgrade":
            await castle_service.upgrade(session, user.id)
            await _castle_view(callback, session)
            notice = "دژ با موفقیت ارتقا پیدا کرد."
        elif callback_data.action == "castle_repair":
            await castle_service.repair(session, user.id)
            await _castle_view(callback, session)
            notice = "دژ با موفقیت تعمیر شد."
        elif callback_data.action == "hospital_instant_recover":
            await hospital_service.instant_recover(
                session, user.id, callback_data.target_id
            )
            await _hospital_view(callback, session)
            notice = "دبیر با پرداخت الماس فوراً درمان شد."
        elif callback_data.action == "hospital_upgrade":
            await hospital_service.upgrade(session, user.id)
            await _hospital_view(callback, session)
            notice = "بیمارستان ارتقا پیدا کرد؛ بستری‌های جدید سریع‌تر درمان می‌شوند."
        elif callback_data.action == "teacher_buy":
            purchased_teacher = await teacher_service.buy(
                session, user.id, callback_data.target_id
            )
            group_purchase = isinstance(
                callback.message, Message
            ) and callback.message.chat.type in {"group", "supergroup"}
            if group_purchase:
                await session.commit()
                await _delete_group_purchase_prompt(callback)
                await callback.message.answer(
                    f"✅ دبیر «{purchased_teacher.teacher.name}» با موفقیت خریداری شد.",
                    reply_to_message_id=(
                        purchase_source.message_id
                        if purchase_source is not None
                        else None
                    ),
                    disable_group_reply=purchase_source is None,
                )
            else:
                if callback_data.origin == "buffet":
                    from app.bot.handlers.buffet import _teacher_shop_view

                    await _teacher_shop_view(callback, session)
                else:
                    await _teachers_view(callback, session)
                if callback.message is not None:
                    await callback.message.answer(
                        f"✅ دبیر «{purchased_teacher.teacher.name}» با موفقیت خریداری شد."
                    )
            notice = "دبیر با موفقیت خریداری شد."
        elif callback_data.action == "teacher_upgrade":
            await teacher_service.upgrade(session, user.id, callback_data.target_id)
            await _teacher_view(callback, session, callback_data.target_id)
            notice = "دبیر با موفقیت ارتقا پیدا کرد."
        elif callback_data.action == "teacher_sell":
            price = await teacher_service.sell(
                session, user.id, callback_data.target_id
            )
            await _teachers_view(callback, session)
            notice = f"دبیر فروخته شد؛ {_number(price)} سکه دریافت کرد."
        else:  # teacher_activate
            await teacher_service.activate(session, user.id, callback_data.target_id)
            await _teacher_view(callback, session, callback_data.target_id)
            notice = "دبیر فعال شد."
        await callback.answer(notice)
    except AttackInProgress:
        await session.rollback()
        await callback.answer(
            "این دبیر در حال نبرد است؛ پس از پایان نبرد می‌توانید او را بفروشید.",
            show_alert=True,
        )
    except InsufficientDiamonds as error:
        await session.rollback()
        if callback_data.action == "teacher_buy":
            await _delete_group_purchase_prompt(callback)
            await callback.answer(_teacher_purchase_error(error), show_alert=True)
        else:
            await callback.answer(
                "الماس کافی برای تعمیر یا ارتقا ندارید.", show_alert=True
            )
    except CastleNeedsRepair:
        await session.rollback()
        await _castle_view(callback, session)
        await callback.answer("اول دژ را تعمیر کن، بعد ارتقا بده.", show_alert=True)
    except (
        TeacherAlreadyOwned,
        TeacherLimitReached,
        TeacherLocked,
        TeacherNotFound,
        TeacherNotPurchasable,
        TeacherSlotLocked,
        InsufficientCoins,
    ) as error:
        await session.rollback()
        if callback_data.action == "teacher_buy":
            await _delete_group_purchase_prompt(callback)
        await callback.answer(_teacher_purchase_error(error), show_alert=True)
    except SchoolError:
        await session.rollback()
        await callback.answer("این عملیات در حال حاضر امکان‌پذیر نیست.", show_alert=True)


@router.callback_query(HospitalCallback.filter())
async def hospital_callback_handler(
    callback: CallbackQuery,
    callback_data: HospitalCallback,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    try:
        user = await _user(session, callback.from_user.id)
        if callback_data.action == "activate":
            await teacher_service.activate(session, user.id, callback_data.teacher_id)
            notice = "دبیر فعال شد."
        elif callback_data.action == "recover":
            await hospital_service.begin_recovery(
                session, user.id, callback_data.teacher_id
            )
            notice = "فرآیند درمان دبیر آغاز شد."
        elif callback_data.action == "discharge":
            await hospital_service.discharge(session, user.id, callback_data.teacher_id)
            notice = "دبیر ترخیص شد و دوباره فعال است."
        elif callback_data.action == "instant":
            cost = hospital_service.instant_recovery_cost()
            if cost is None:
                raise SchoolError
            owned = await teacher_service.get_owned(
                session, user.id, callback_data.teacher_id
            )
            await _send_or_edit(
                callback,
                f"⚡ درمان فوری دبیر «{owned.teacher.name}»\n\n"
                f"هزینه: {_number(cost)} 💎\n"
                "با پرداخت الماس، دبیر فوراً کاملاً درمان می‌شود.\n"
                "آیا ادامه می‌دهی؟",
                reply_markup=confirmation_keyboard(
                    action="hospital_instant_recover", target_id=owned.id
                ),
            )
            await callback.answer()
            return
        elif callback_data.action == "upgrade":
            hospital = await hospital_service.snapshot(session, user.id)
            if hospital.upgrade_cost is None:
                raise HospitalUpgradeUnavailable
            reward = hospital_service.config.upgrade_banana_reward(
                hospital.upgrade_cost
            )
            can_confirm = hospital.player_level >= (hospital.required_player_level or 1)
            reply_markup = (
                confirmation_keyboard(action="hospital_upgrade", target_id=0)
                if can_confirm
                else InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="بازگشت به بیمارستان",
                                icon_custom_emoji_id="5235864325540815679",
                                style="danger",
                                callback_data=ConfirmationCallback(
                                    action="hospital_upgrade",
                                    target_id=0,
                                    decision="cancel",
                                ).pack(),
                            )
                        ]
                    ]
                )
            )
            await _send_or_edit(
                callback,
                f"{emoji('5866060208253441223', '⬆️')} {bold('ارتقای بیمارستان')}\n\n"
                f"{escape('سطح:')} {escape(_number(hospital.level))} {emoji('5235470399730361615', '➡️')} {escape(_number(hospital.level + 1))}\n"
                f"{emoji('5275983061001977055', '🛏')} {escape('تخت‌ها:')} {escape(_number(hospital.capacity))} {emoji('5235470399730361615', '➡️')} {escape(_number(hospital.next_capacity))}\n"
                f"{emoji('6039539366177541657', '⏳')} {bold('سرعت درمان بیمارستان')}\n"
                f"> {bold(f'{hospital.heal_hp_per_hour} HP در ساعت')} {emoji('5235470399730361615', '➡️')} {bold(f'{hospital.next_heal_hp_per_hour} HP در ساعت')}\n\n"
                f"{emoji('5825570280243732195', '🩸')} {escape('نمونه برای 80 HP آسیب:')} "
                f"{escape(_duration_text(hospital_service.config.hospital_recovery_minutes(hospital.level, 80)))} "
                f"{emoji('5235470399730361615', '➡️')} "
                f"{escape(_duration_text(hospital_service.config.hospital_recovery_minutes(hospital.level + 1, 80)))}\n\n"
                f"{emoji('5825753314570018832', '💎')} {escape('هزینه:')} {escape(_number(hospital.upgrade_cost))} {escape('الماس')}\n"
                f"{emoji('5902520589356113908', '🍌')} {escape('پاداش:')} {escape(_number(reward))} {escape('موز')}\n\n"
                f"{escape('سطح فرمانده لازم:')} {escape(_number(hospital.required_player_level))}\n\n"
                f"{bold('ارتقا را تأیید می‌کنی؟' if can_confirm else 'این ارتقا هنوز برای سطح شما باز نشده است.')}",
                reply_markup=reply_markup,
                parse_mode=MARKDOWN_V2,
            )
            await callback.answer()
            return
        elif callback_data.action == "back":
            await _school_view(callback, session)
            await callback.answer()
            return
        else:
            notice = None
        await _hospital_view(callback, session)
        await callback.answer(notice)
    except HospitalFull:
        await callback.answer(
            "تخت‌های بیمارستان پر هستند. دبیر درمان‌شده را ترخیص کن یا بیمارستان را ارتقا بده.",
            show_alert=True,
        )
    except SchoolError:
        await callback.answer("این عملیات در حال حاضر امکان‌پذیر نیست.", show_alert=True)
