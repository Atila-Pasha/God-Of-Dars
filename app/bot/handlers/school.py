from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

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
)
from app.bot.keyboards.school import (
    castle_keyboard,
    confirmation_keyboard,
    hospital_keyboard,
    school_keyboard,
    teacher_catalog_keyboard,
    teacher_detail_keyboard,
    teachers_keyboard,
)
from app.bot.utils.telegram import safe_edit_text
from app.core.enums import TeacherStatus
from app.models.user_teacher import UserTeacher
from app.services.castle_service import CastleService
from app.services.recovery_service import HospitalService
from app.services.school_errors import SchoolError
from app.services.teacher_service import TeacherService
from app.services.user_service import UserInactiveError, UserService

router = Router(name="school")
user_service = UserService()
castle_service = CastleService()
teacher_service = TeacherService()
hospital_service = HospitalService(castle_service=castle_service)

SCHOOL_LABEL = next(
    label for label, section in MENU_SECTION_BY_LABEL.items() if section == "school"
)
STATUS_LABELS = {
    TeacherStatus.ACTIVE: "فعال",
    TeacherStatus.INJURED: "مصدوم",
    TeacherStatus.DISABLED: "غیرفعال",
    TeacherStatus.RECOVERING: "در حال بهبودی",
}
STATUS_ICONS = {
    TeacherStatus.ACTIVE: "🟢",
    TeacherStatus.INJURED: "🟠",
    TeacherStatus.DISABLED: "🔴",
    TeacherStatus.RECOVERING: "🔵",
}
PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _number(value: int) -> str:
    return str(value)


def _progress_bar(value: int, maximum: int, *, width: int = 10) -> str:
    if maximum <= 0:
        return "-" * width
    filled = round(max(0, min(value, maximum)) / maximum * width)
    return "█" * filled + "░" * (width - filled)


def _progress_percent(value: int, maximum: int) -> str:
    if maximum <= 0:
        return "—"
    return _number(round(max(0, min(value, maximum)) / maximum * 100)) + "%"


async def _user(session: AsyncSession, telegram_user_id: int):
    return await user_service.get_active_by_telegram_user_id(session, telegram_user_id)


def _status(teacher: UserTeacher) -> str:
    return STATUS_LABELS.get(teacher.status, teacher.status.value)


def _status_icon(teacher: UserTeacher) -> str:
    return STATUS_ICONS.get(teacher.status, "⚪")


def _recovery_text(teacher: UserTeacher) -> str:
    recovery = next(
        (item for item in teacher.recoveries if item.completed_at is None), None
    )
    if recovery is None:
        return "زمان بهبودی: تنظیم نشده"
    end_at = recovery.recovery_end_at
    if end_at.tzinfo is None:
        end_at = end_at.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return f"پایان بهبودی: {end_at.astimezone().strftime('%Y-%m-%d %H:%M')}"


async def _send_or_edit(
    target: Message | CallbackQuery,
    text: str,
    *,
    reply_markup,
) -> None:
    if isinstance(target, CallbackQuery):
        if target.message is None:
            return
        try:
            await safe_edit_text(target.message, text, reply_markup=reply_markup)
        except TelegramAPIError:
            await target.message.answer(text, reply_markup=reply_markup)
        return
    await target.answer(text, reply_markup=reply_markup)


async def _school_view(
    target: Message | CallbackQuery,
    session: AsyncSession,
) -> None:
    user = await _user(session, target.from_user.id)
    castle = await castle_service.snapshot(session, user.id)
    capacity = await teacher_service.capacity(session, user.id)
    text = (
        " 🏫 مدرسه من \n\n"
        f"🎖 سطح بازیکن: {_number(user.level)}\n"
        f"🏰 سطح دژ: {_number(castle.level)}\n"
        f"🛡 قدرت دفاعی: {_number(castle.strength)}\n\n"
        "📚 وضعیت دبیرها\n\n"
        f"{_progress_bar(capacity.owned, capacity.available)}  "
        f"{_number(capacity.owned)} / {_number(capacity.available)} "
        f"({_progress_percent(capacity.owned, capacity.available)})"
    )
    await _send_or_edit(target, text, reply_markup=school_keyboard())


async def _castle_view(
    target: CallbackQuery,
    session: AsyncSession,
) -> None:
    user = await _user(session, target.from_user.id)
    castle = await castle_service.snapshot(session, user.id)
    text = (
        " 🏰 دژ مدرسه \n\n"
        f"✨ سطح دژ: {_number(castle.level)}\n"
        f"⚔️ قدرت دژ: {_number(castle.strength)}\n"
        f"🛡 قدرت سیستم دفاعی: {_number(castle.defense_power)}\n\n"
        "🏗️ وضعیت دفاعی\n"
        f"قدرت کلی: {_number(castle.strength + castle.defense_power)} واحد"
    )
    await _send_or_edit(
        target,
        text,
        reply_markup=castle_keyboard(castle_service.can_upgrade_level(castle.level)),
    )


async def _teachers_view(
    target: Message | CallbackQuery,
    session: AsyncSession,
    *,
    from_buffet: bool = False,
) -> None:
    user = await _user(session, target.from_user.id)
    capacity = await teacher_service.capacity(session, user.id)
    teachers = await teacher_service.owned(session, user.id)
    catalog = await teacher_service.catalog(session, user.id)
    free_slots = max(capacity.available - capacity.owned, 0)
    text_lines = [
        "👨‍🏫 دبیرهای من \n\n",
        "",
        f"🎖 سطح شما: {_number(user.level)}",
        "",
        "📊 ظرفیت استفاده‌شده",
        (
            f"{_progress_bar(capacity.owned, capacity.available)}  "
            f"{_number(capacity.owned)} / {_number(capacity.available)} "
            f"({_progress_percent(capacity.owned, capacity.available)})"
        ),
        f"🪑 جای خالی: {_number(free_slots)}",
        "📌 ظرفیت نهایی از مجموع ظرفیت دبیرهای خریداری‌شده محاسبه می‌شود.",
        "",
    ]
    if capacity.available < capacity.maximum:
        text_lines.append(
            f"🔒 {_number(capacity.maximum - capacity.available)} جایگاه با Level بالاتر باز می‌شود."
        )
    if teachers:
        text_lines.append("👥 فهرست دبیرها")
        for teacher in teachers:
            text_lines.extend(
                [
                    "",
                    (
                        f"{_status_icon(teacher)} {teacher.teacher.name}  •  "
                        f"Level {_number(teacher.level)}"
                    ),
                    (
                        f"HP  {_progress_bar(teacher.current_hp, teacher.teacher.max_hp, width=8)} "
                        f"{_number(teacher.current_hp)} / {_number(teacher.teacher.max_hp)}"
                    ),
                    f"وضعیت: {_status(teacher)}",
                ]
            )
    else:
        text_lines.append("🌱 هنوز دبیری به مدرسه‌تان اضافه نشده است.")
    await _send_or_edit(
        target,
        "\n".join(text_lines),
        reply_markup=teachers_keyboard(
            teachers,
            catalog,
            can_buy=from_buffet
            and (
                capacity.owned < capacity.available
                and capacity.owned < capacity.maximum
                and any(teacher.unlock_level <= user.level for teacher in catalog)
            ),
            back_action="back_buffet" if from_buffet else "back_school",
        ),
    )


async def _teacher_view(
    target: CallbackQuery,
    session: AsyncSession,
    user_teacher_id: int,
) -> None:
    user = await _user(session, target.from_user.id)
    teacher = await teacher_service.get_owned(session, user.id, user_teacher_id)
    damage = "تنظیم نشده"
    try:
        damage = str(teacher_service.damage(teacher))
    except SchoolError:
        pass
    damage_text = damage if damage == "تنظیم نشده" else _number(int(damage))
    text = (
        f"{_status_icon(teacher)} {teacher.teacher.name}\n\n"
        f"🎖 Level: {_number(teacher.level)}\n"
        f"⚔️ Damage: {damage_text}\n"
        f"❤️ HP: {_progress_bar(teacher.current_hp, teacher.teacher.max_hp)}\n"
        f"   {_number(teacher.current_hp)} / {_number(teacher.teacher.max_hp)} "
        f"({_progress_percent(teacher.current_hp, teacher.teacher.max_hp)})\n"
        f"📌 وضعیت: {_status(teacher)}\n"
        f"✨ توانایی: {teacher.teacher.ability_text or 'تنظیم نشده'}\n\n"
        f"⏳ {_recovery_text(teacher)}"
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
    )


async def _hospital_view(
    target: CallbackQuery,
    session: AsyncSession,
) -> None:
    user = await _user(session, target.from_user.id)
    patients = await hospital_service.patients(session, user.id)
    lines = [
        "🏥 بیمارستان مدرسه \n\n",
        "",
    ]
    if not patients:
        lines.append("در حال حاضر دبیر مصدوم یا غیرفعالی ندارید.")
    else:
        for teacher in patients:
            lines.extend(
                [
                    (
                        f"{_status_icon(teacher)} {teacher.teacher.name}  •  "
                        f"{_status(teacher)}"
                    ),
                    (
                        f"❤️ {_progress_bar(teacher.current_hp, teacher.teacher.max_hp, width=8)} "
                        f"{_number(teacher.current_hp)} / {_number(teacher.teacher.max_hp)}"
                    ),
                    f"⏳ {_recovery_text(teacher)}",
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
        ),
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
            upgrade = castle_service.config.castle_upgrade(castle.level)
            await _send_or_edit(
                callback,
                f"⬆️ ارتقای دژ\n\n"
                f"هزینه: {_number(upgrade.coin_cost)} سکه\n"
                "آیا می‌خواهی ارتقای دژ را انجام بدهم؟",
                reply_markup=confirmation_keyboard(
                    action="castle_upgrade", target_id=0
                ),
            )
            await callback.answer()
            return
        else:
            await _castle_view(callback, session)
        await callback.answer(notice)
    except SchoolError:
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
        elif callback_data.action == "buy":
            teacher = await teacher_service.catalog_teacher(
                session, callback_data.teacher_id
            )
            await _send_or_edit(
                callback,
                f"🛒 خرید دبیر {teacher.name}\n\n"
                f"قیمت: {_number(teacher.purchase_price)} سکه\n"
                "آیا می‌خواهی این دبیر را بخری؟",
                reply_markup=confirmation_keyboard(
                    action="teacher_buy",
                    target_id=teacher.id,
                    origin=callback_data.origin,
                ),
            )
            await callback.answer()
        elif callback_data.action == "upgrade":
            owned = await teacher_service.get_owned(
                session, user.id, callback_data.teacher_id
            )
            await _send_or_edit(
                callback,
                f"⬆️ ارتقای دبیر {owned.teacher.name}\n\n"
                f"هزینه: {_number(owned.teacher.upgrade_price)} سکه\n"
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
            cost = hospital_service.config.teacher_activation_cost
            if cost is None:
                raise SchoolError
            owned = await teacher_service.get_owned(
                session, user.id, callback_data.teacher_id
            )
            await _send_or_edit(
                callback,
                f"⚡ فعال‌سازی دبیر {owned.teacher.name}\n\n"
                f"هزینه: {_number(cost)} سکه\n"
                "آیا می‌خواهی دبیر را فعال کنم؟",
                reply_markup=confirmation_keyboard(
                    action="teacher_activate", target_id=owned.id
                ),
            )
            await callback.answer()
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
    try:
        user = await _user(session, callback.from_user.id)
        if callback_data.decision == "cancel":
            if callback_data.action == "castle_upgrade":
                await _castle_view(callback, session)
            else:
                await _teachers_view(
                    callback,
                    session,
                    from_buffet=callback_data.origin == "buffet",
                )
            await callback.answer("عملیات لغو شد.")
            return

        if callback_data.action == "castle_upgrade":
            await castle_service.upgrade(session, user.id)
            await _castle_view(callback, session)
            notice = "دژ با موفقیت ارتقا پیدا کرد."
        elif callback_data.action == "teacher_buy":
            await teacher_service.buy(session, user.id, callback_data.target_id)
            await _teachers_view(
                callback,
                session,
                from_buffet=callback_data.origin == "buffet",
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
    except SchoolError:
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
            notice = "فرآیند بهبودی دبیر آغاز شد."
        elif callback_data.action == "back":
            await _school_view(callback, session)
            await callback.answer()
            return
        else:
            notice = None
        await _hospital_view(callback, session)
        await callback.answer(notice)
    except SchoolError:
        await callback.answer("این عملیات در حال حاضر امکان‌پذیر نیست.", show_alert=True)
