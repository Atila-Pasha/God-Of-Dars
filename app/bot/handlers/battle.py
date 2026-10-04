from contextlib import suppress
from datetime import UTC, datetime
from typing import Literal

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyParameters,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.banners import (
    MARKDOWN_V2,
    TEACHERS,
    attack_launch_banner,
    attack_preview_banner,
    attack_result_banner,
    bold,
    emoji,
    escape,
    section_entry_banner,
)
from app.bot.callbacks import (
    AttackConfirmationCallback,
    AttackCountdownCallback,
    AttackMenuCallback,
    RandomAttackCallback,
)
from app.bot.custom_emojis import reset_persist_group_message, set_persist_group_message
from app.bot.keyboards.main_menu import section_back_keyboard
from app.bot.states import AttackMenuStates
from app.bot.utils.telegram import safe_edit_text
from app.core.enums import AttackStatus
from app.models.attack import Attack
from app.models.user import User
from app.services.attack_service import (
    AttackPreview,
    AttackResult,
    AttackService,
    RandomAttackPreview,
)
from app.services.school_errors import (
    AttackerNotRegistered,
    AttackInProgress,
    AttackTargetNotRegistered,
    CannotAttackSelf,
    InsufficientCoins,
    InvalidTeacherState,
    RandomAttackSelectionExpired,
    RandomOpponentNotFound,
    SchoolError,
    SchoolUserNotFound,
    ShieldAlreadyActive,
    TargetProtectedByShield,
    TeacherInHospital,
    TeacherNotOwned,
)

router = Router(name="battle")
attack_service = AttackService()
MAX_ATTACK_TEACHERS = attack_service.config.max_attack_teachers


def _source_group_chat_id(message: Message) -> int | None:
    chat = getattr(message, "chat", None)
    return (
        chat.id if chat is not None and chat.type in {"group", "supergroup"} else None
    )


def _attack_countdown_keyboard(command_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="زمان باقی‌مانده",
                    icon_custom_emoji_id="5825746176334373354",
                    callback_data=AttackCountdownCallback(command_id=command_id).pack(),
                )
            ]
        ]
    )


async def _send_launch_message(
    message: Message,
    launch,
    session: AsyncSession,
    reply_parameters: ReplyParameters | None,
) -> None:
    token = set_persist_group_message()
    try:
        kwargs = {
            "reply_parameters": reply_parameters,
            "reply_markup": _attack_countdown_keyboard(launch.attack_command_id),
            "parse_mode": MARKDOWN_V2,
        }
        try:
            sent = await message.answer(
                attack_launch_banner(launch.target_name, launch.teacher_details),
                **kwargs,
            )
        except TelegramBadRequest as exc:
            if "message to be replied not found" not in str(exc).lower():
                raise
            kwargs["reply_parameters"] = None
            sent = await message.answer(
                attack_launch_banner(launch.target_name, launch.teacher_details),
                **kwargs,
            )
    finally:
        reset_persist_group_message(token)
    await session.execute(
        update(Attack)
        .where(Attack.attack_command_id == launch.attack_command_id)
        .values(launch_chat_id=sent.chat.id, launch_message_id=sent.message_id)
    )
    await session.commit()


@router.callback_query(AttackCountdownCallback.filter())
async def attack_countdown(
    callback: CallbackQuery,
    callback_data: AttackCountdownCallback,
    session: AsyncSession,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    rows = list(
        await session.scalars(
            select(Attack)
            .where(Attack.attack_command_id == callback_data.command_id)
            .order_by(Attack.id)
        )
    )
    if not rows:
        await callback.answer("این حمله پیدا نشد.", show_alert=True)
        return
    attacker_id = await session.scalar(
        select(User.telegram_user_id).where(User.id == rows[0].attacker_id)
    )
    if callback.from_user.id != attacker_id:
        await callback.answer(
            "فقط فرماندهٔ حمله می‌تواند زمان را بررسی کند.", show_alert=True
        )
        return
    if all(row.status is AttackStatus.RESOLVED for row in rows):
        await callback.answer("حمله تمام شده است.", show_alert=True)
        return
    target_name = (
        await session.scalar(
            select(User.first_name).where(User.id == rows[0].target_id)
        )
        or "حریف"
    )
    details = tuple(
        (
            row.teacher_name_snapshot or "دبیر",
            row.teacher_ability_snapshot,
            row.teacher_emoji_snapshot,
        )
        for row in rows
    )
    remaining = max(
        0, int((rows[0].resolve_at - datetime.now(UTC)).total_seconds() + 0.999)
    )
    await callback.answer(f"{remaining // 60:02d}:{remaining % 60:02d} باقی مانده")
    token = set_persist_group_message()
    try:
        await safe_edit_text(
            callback.message,
            attack_launch_banner(target_name, details, remaining_seconds=remaining),
            reply_markup=_attack_countdown_keyboard(callback_data.command_id),
            parse_mode=MARKDOWN_V2,
        )
    finally:
        reset_persist_group_message(token)


def _attack_text(result: AttackResult) -> str:
    return attack_result_banner(result)


def _preview_content(preview: AttackPreview) -> str:
    return attack_preview_banner(preview)


def _preview_text(preview: AttackPreview) -> str:
    return _preview_content(preview)


def _attack_help_text(*, group: bool = False) -> str:
    if group:
        return (
            "⚔️ راهنمای حمله در گروه\n\n"
            "روی پیام هدف Reply بزن و یکی از این قالب‌ها را بفرست:\n"
            "• حمله (برای انتخاب چند دبیر)\n"
            "• حمله {اسم دبیر}\n"
            "• حمله رندوم {اسم دبیر}\n\n"
            "اگر روی پیام هدف Reply نزنی:\n"
            "• حمله {نام‌کاربری هدف} {اسم دبیر}"
        )
    return (
        "⚔️ راهنمای حمله در گفت‌وگوی خصوصی\n\n"
        "حمله {نام‌کاربری هدف} {اسم دبیر}\n"
        "مثال: حمله @player افلاطون\n\n"
        "در گروه، روی پیام هدف Reply بزن و بنویس:\n"
        "حمله {اسم دبیر}\n"
        "حمله رندوم {اسم دبیر}"
    )


def _attack_confirmation_keyboard(
    preview: AttackPreview, *, source_message_id: int
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تأیید حمله",
                    style="success",
                    callback_data=AttackConfirmationCallback(
                        attacker_id=preview.attacker_id,
                        target_id=preview.target_id,
                        teacher_id=preview.teacher_id,
                        decision="confirm",
                        teacher_ids=preview.teacher_ids,
                        source_message_id=source_message_id,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="❌ لغو",
                    style="danger",
                    callback_data=AttackConfirmationCallback(
                        attacker_id=preview.attacker_id,
                        target_id=preview.target_id,
                        teacher_id=preview.teacher_id,
                        decision="cancel",
                        teacher_ids=preview.teacher_ids,
                        source_message_id=source_message_id,
                    ).pack(),
                ),
            ]
        ]
    )


def _random_attack_preview_content(selection: RandomAttackPreview) -> str:
    remaining_seconds = max(
        0, int((selection.expires_at - datetime.now(UTC)).total_seconds())
    )
    remaining_minutes = max(1, (remaining_seconds + 59) // 60)
    return (
        attack_preview_banner(selection.preview)
        + "\n\n"
        + f"{emoji('5823192436024813346', '🎲')} حریف تا حدود {remaining_minutes} دقیقه ثابت می‌ماند\n"
        + f"{emoji('6039539366177541657', '♻️')} دیدن حریف دیگر: {escape(selection.reroll_coin_cost)} سکه"
    )


def _random_attack_preview_text(selection: RandomAttackPreview) -> str:
    return _random_attack_preview_content(selection)


def _random_attack_confirmation_keyboard(
    selection: RandomAttackPreview, *, source_message_id: int
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تأیید حمله",
                    style="success",
                    callback_data=RandomAttackCallback(
                        action="confirm",
                        attacker_id=selection.preview.attacker_id,
                        version=selection.version,
                        source_message_id=source_message_id,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="❌ لغو",
                    style="danger",
                    callback_data=RandomAttackCallback(
                        action="cancel",
                        attacker_id=selection.preview.attacker_id,
                        version=selection.version,
                        source_message_id=source_message_id,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"♻️ حریف دیگر ({selection.reroll_coin_cost} 🪙)",
                    callback_data=RandomAttackCallback(
                        action="reroll",
                        attacker_id=selection.preview.attacker_id,
                        version=selection.version,
                        source_message_id=source_message_id,
                    ).pack(),
                )
            ],
        ]
    )


def _teacher_selection_keyboard(
    teachers,
    *,
    mode: Literal["random", "id"],
    selected_ids: list[int],
    attacker_id: int = 0,
) -> InlineKeyboardMarkup:
    selected = set(selected_ids)
    rows = [
        [
            InlineKeyboardButton(
                text=f"{teacher.teacher.name} (سطح {teacher.level})",
                icon_custom_emoji_id=(
                    "5825709849500985213" if teacher.id in selected else None
                ),
                callback_data=AttackMenuCallback(
                    action="toggle",
                    mode=mode,
                    teacher_id=teacher.id,
                    attacker_id=attacker_id,
                ).pack(),
            )
        ]
        for teacher in teachers
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="تأیید حمله",
                style="success",
                icon_custom_emoji_id="5823388325188214894",
                callback_data=AttackMenuCallback(
                    action="submit", mode=mode, attacker_id=attacker_id
                ).pack(),
            ),
            InlineKeyboardButton(
                text="لغو حمله",
                style="danger",
                icon_custom_emoji_id="5825504038963125908",
                callback_data=AttackMenuCallback(
                    action="cancel", mode=mode, attacker_id=attacker_id
                ).pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _attack_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="حمله رندوم",
                    icon_custom_emoji_id="5825935099060822018",
                    callback_data=AttackMenuCallback(
                        action="choose", mode="random"
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="🎯 حمله با آیدی",
                    callback_data=AttackMenuCallback(action="choose", mode="id").pack(),
                ),
            ]
        ]
    )


async def _show_teacher_selection(
    target: Message | CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    *,
    mode: Literal["random", "id"],
    reply_to_message_id: int | None = None,
) -> None:
    if target.from_user is None:
        return
    try:
        teachers = await attack_service.available_attack_teachers(
            session, attacker_telegram_id=target.from_user.id
        )
    except SchoolError as error:
        message = target.message if isinstance(target, CallbackQuery) else target
        if isinstance(message, Message):
            await _report_error(message, error)
        return
    if not teachers:
        message = target.message if isinstance(target, CallbackQuery) else target
        if isinstance(message, Message):
            await message.answer(
                "دبیر فعال و سالمی برای حمله ندارید. ابتدا دبیرتان را فعال یا درمان کنید."
            )
        return
    data = await state.get_data()
    selected_ids = [
        teacher_id
        for teacher_id in data.get("selected_teacher_ids", [])
        if any(teacher.id == teacher_id for teacher in teachers)
    ]
    await state.update_data(mode=mode, selected_teacher_ids=selected_ids)
    await state.set_state(AttackMenuStates.selecting_teachers)
    text = (
        f"{TEACHERS} {bold('دبیرهای حمله را انتخاب کنید.')}\n\n"
        f"> می‌توانید هم‌زمان تا {MAX_ATTACK_TEACHERS} دبیر را تیک بزنید\\."
    )
    markup = _teacher_selection_keyboard(
        teachers,
        mode=mode,
        selected_ids=selected_ids,
        attacker_id=target.from_user.id,
    )
    if isinstance(target, CallbackQuery):
        if isinstance(target.message, Message):
            await target.message.edit_text(
                text, reply_markup=markup, parse_mode=MARKDOWN_V2
            )
    else:
        await target.answer(
            text,
            reply_markup=markup,
            reply_to_message_id=reply_to_message_id,
            parse_mode=MARKDOWN_V2,
        )


async def _send_result(message: Message, result: AttackResult) -> None:
    await message.answer(_attack_text(result), parse_mode=MARKDOWN_V2)
    bot = message.bot
    if bot is not None:
        with suppress(TelegramAPIError):
            await bot.send_message(
                result.target_telegram_id,
                attack_result_banner(result, recipient="defender"),
                parse_mode=MARKDOWN_V2,
            )


async def _report_error(message: Message, error: Exception) -> None:
    if isinstance(error, AttackerNotRegistered):
        await message.answer("ابتدا ربات را با /start فعال کنید، سپس حمله را بفرستید.")
    elif isinstance(error, AttackTargetNotRegistered):
        await message.answer(
            "این کاربر هنوز ربات را استارت نکرده است یا حسابش فعال نیست."
        )
    elif isinstance(error, SchoolUserNotFound):
        await message.answer("اطلاعات کاربر پیدا نشد.")
    elif isinstance(error, TeacherNotOwned):
        await message.answer("این دبیر را هنوز نخریده‌اید.")
    elif isinstance(error, TeacherInHospital):
        await message.answer("این دبیر در حال بهبود است و فعلاً نمی‌تواند حمله کند.")
    elif isinstance(error, AttackInProgress):
        await message.answer(
            "⚔️ حمله فعال دارید؛ پس از پایان آن می‌توانید دوباره حمله کنید."
        )
    elif isinstance(error, (ShieldAlreadyActive, TargetProtectedByShield)):
        await message.answer(
            "🛡 این بازیکن سپر فعال دارد و فعلاً نمی‌توان به او حمله کرد."
        )
    elif isinstance(error, InvalidTeacherState):
        await message.answer(
            "این دبیر فعال نیست؛ ابتدا آن را فعال کنید تا آماده حمله شود."
        )
    elif isinstance(error, CannotAttackSelf):
        await message.answer(
            f"نمیتونی به خودت حمله کنی زرنگ {emoji('5920515596088250243', '😏')}",
            parse_mode=MARKDOWN_V2,
        )
    elif isinstance(error, RandomOpponentNotFound):
        await message.answer("حریفی برای حمله پیدا نکردم.")
    elif isinstance(error, RandomAttackSelectionExpired):
        await message.answer(
            "این انتخاب دیگر معتبر نیست؛ دوباره «حمله رندوم {اسم دبیر}» را بفرستید."
        )
    elif isinstance(error, InsufficientCoins):
        await message.answer("برای دیدن حریف دیگر، سکه کافی ندارید.")
    else:
        await message.answer("اجرای حمله ممکن نبود؛ لطفاً مشخصات حمله را بررسی کنید.")


@router.message(Command("attack"))
async def attack_help_handler(message: Message) -> None:
    await message.answer(
        _attack_help_text(group=message.chat.type in {"group", "supergroup"})
    )


@router.message(F.chat.type == "private", F.text == "حمله")
async def attack_menu_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        section_entry_banner("حمله"),
        reply_markup=section_back_keyboard(),
        parse_mode=MARKDOWN_V2,
    )
    await message.answer(
        "انتخاب نوع حمله\n\nیکی از روش‌های زیر را انتخاب کنید:",
        reply_markup=_attack_type_keyboard(),
    )


@router.message(F.chat.type == "private", F.text == "حمله رندوم")
async def random_attack_menu_handler(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    await state.update_data(mode="random", selected_teacher_ids=[])
    await message.answer(
        "برای بازگشت، دکمه زیر را بزنید.", reply_markup=section_back_keyboard()
    )
    await _show_teacher_selection(message, session, state, mode="random")


@router.message(F.chat.type == "private", F.text == "حمله با آیدی")
async def id_attack_menu_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AttackMenuStates.waiting_target)
    await message.answer(
        "🎯 آیدی کاربر هدف را بفرستید.\n\n"
        "می‌توانید نام کاربری مثل @player یا آیدی عددی تلگرام را وارد کنید.",
        reply_markup=section_back_keyboard(),
    )


@router.message(AttackMenuStates.waiting_target)
async def attack_target_handler(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    if message.from_user is None or not message.text:
        return
    try:
        target = await attack_service.target_preview(
            session,
            attacker_telegram_id=message.from_user.id,
            identifier=message.text,
        )
    except SchoolError as error:
        await _report_error(message, error)
        return
    await state.update_data(
        mode="id",
        target_id=target.id,
        selected_teacher_ids=[],
    )
    username = f"@{target.username}" if target.username else "ثبت نشده"
    await message.answer(
        "🎯 پیش‌نمایش هدف حمله\n\n"
        f"👤 نام: {target.first_name}\n"
        f"🆔 نام کاربری: {username}\n"
        f"🔢 آیدی تلگرام: {target.telegram_user_id}\n\n"
        "برای ادامه، دبیرهای حمله را انتخاب کنید.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👨‍🏫 انتخاب دبیرها و حمله",
                        callback_data=AttackMenuCallback(
                            action="target_teachers", mode="id"
                        ).pack(),
                    )
                ]
            ]
        ),
    )


@router.callback_query(AttackMenuCallback.filter())
async def attack_menu_callback_handler(
    callback: CallbackQuery,
    callback_data: AttackMenuCallback,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    if callback_data.attacker_id and callback_data.attacker_id != callback.from_user.id:
        await callback.answer(
            "فقط شروع‌کننده حمله می‌تواند دبیرها را انتخاب کند.", show_alert=True
        )
        return
    data = await state.get_data()
    if (
        data.get("group_attacker_id") is not None
        and data["group_attacker_id"] != callback.from_user.id
    ):
        await callback.answer(
            "فقط شروع‌کننده حمله می‌تواند دبیرها را انتخاب کند.", show_alert=True
        )
        return
    if callback_data.action == "cancel":
        await state.clear()
        await callback.answer("حمله لغو شد.")
        await callback.message.edit_text("حمله لغو شد.", reply_markup=None)
        return
    if callback_data.action == "choose":
        await state.clear()
        await state.update_data(mode=callback_data.mode, selected_teacher_ids=[])
        if callback_data.mode == "random":
            await callback.answer()
            await _show_teacher_selection(callback, session, state, mode="random")
        else:
            await state.set_state(AttackMenuStates.waiting_target)
            await callback.message.edit_text(
                "🎯 آیدی کاربر هدف را بفرستید.\n\n"
                "می‌توانید نام کاربری مثل @player یا آیدی عددی تلگرام را وارد کنید."
            )
            await callback.answer()
        return
    if data.get("mode") != callback_data.mode:
        await callback.answer(
            "این منوی حمله دیگر معتبر نیست؛ دوباره از منوی اصلی وارد شوید.",
            show_alert=True,
        )
        return
    if callback_data.action == "target_teachers":
        await callback.answer()
        await _show_teacher_selection(callback, session, state, mode=callback_data.mode)
        return

    try:
        teachers = await attack_service.available_attack_teachers(
            session, attacker_telegram_id=callback.from_user.id
        )
    except SchoolError as error:
        await callback.answer()
        await _report_error(callback.message, error)
        return
    available_ids = {teacher.id for teacher in teachers}
    selected_ids = [
        teacher_id
        for teacher_id in data.get("selected_teacher_ids", [])
        if teacher_id in available_ids
    ]

    if callback_data.action == "toggle":
        if callback_data.teacher_id not in available_ids:
            await callback.answer("این دبیر دیگر آماده حمله نیست.", show_alert=True)
            return
        if callback_data.teacher_id in selected_ids:
            selected_ids.remove(callback_data.teacher_id)
        elif len(selected_ids) >= MAX_ATTACK_TEACHERS:
            await callback.answer(
                f"حداکثر {MAX_ATTACK_TEACHERS} دبیر را می‌توانید انتخاب کنید.",
                show_alert=True,
            )
            return
        else:
            selected_ids.append(callback_data.teacher_id)
        await state.update_data(selected_teacher_ids=selected_ids)
        await callback.message.edit_reply_markup(
            reply_markup=_teacher_selection_keyboard(
                teachers,
                mode=callback_data.mode,
                selected_ids=selected_ids,
                attacker_id=callback.from_user.id,
            )
        )
        await callback.answer()
        return

    if not selected_ids:
        await callback.answer("حداقل یک دبیر را انتخاب کنید.", show_alert=True)
        return
    await callback.answer()
    try:
        if callback_data.mode == "random":
            selection = await attack_service.prepare_random_preview_by_teacher_ids(
                session,
                attacker_telegram_id=callback.from_user.id,
                teacher_ids=selected_ids,
            )
            text = _random_attack_preview_content(selection)
            keyboard = _random_attack_confirmation_keyboard(
                selection, source_message_id=0
            )
        else:
            target_id = data.get("target_id")
            if not isinstance(target_id, int):
                await callback.message.answer(
                    "هدف حمله مشخص نیست؛ دوباره از منوی حمله شروع کنید."
                )
                return
            preview = await attack_service.preview_by_teacher_ids(
                session,
                attacker_telegram_id=callback.from_user.id,
                target_id=target_id,
                teacher_ids=selected_ids,
            )
            text = _preview_content(preview)
            keyboard = _attack_confirmation_keyboard(preview, source_message_id=0)
    except SchoolError as error:
        await _report_error(callback.message, error)
        return
    await state.clear()
    with suppress(TelegramAPIError):
        await callback.message.delete()
    await callback.message.answer(text, reply_markup=keyboard, parse_mode=MARKDOWN_V2)


@router.message(F.text.regexp(r"^\s*حمله(?:\s+\S.*)?$"))
async def attack_message(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    if message.from_user is None:
        return
    text = (message.text or "").strip()
    arguments = text.partition(" ")[2].strip()
    if not arguments and not (
        message.chat.type in {"group", "supergroup"}
        and message.reply_to_message is not None
    ):
        await message.answer(
            _attack_help_text(group=message.chat.type in {"group", "supergroup"})
        )
        return
    if not arguments:
        replied = message.reply_to_message
        if replied is None or replied.from_user is None or replied.from_user.is_bot:
            await message.answer("روی پیام کاربر هدف ریپلای کنید و «حمله» بنویسید.")
            return
        if replied.from_user.id == message.from_user.id:
            await _report_error(message, CannotAttackSelf())
            return
        try:
            target = await attack_service.target_preview(
                session,
                attacker_telegram_id=message.from_user.id,
                identifier=str(replied.from_user.id),
            )
        except SchoolError as error:
            await _report_error(message, error)
            return
        await state.clear()
        await state.update_data(
            mode="id",
            target_id=target.id,
            selected_teacher_ids=[],
            group_attacker_id=message.from_user.id,
        )
        await _show_teacher_selection(
            message,
            session,
            state,
            mode="id",
            reply_to_message_id=message.message_id,
        )
        return
    try:
        random_selection: RandomAttackPreview | None = None
        if arguments.casefold().startswith("رندوم"):
            random_teacher = arguments[len("رندوم") :].strip()
            if not random_teacher:
                await message.answer(
                    "برای حمله رندوم نام دبیر را هم بنویسید؛ مثال: حمله رندوم افلاطون"
                )
                return
            random_selection = await attack_service.prepare_random_preview(
                session,
                attacker_telegram_id=message.from_user.id,
                teacher_name=random_teacher,
            )
            preview = random_selection.preview
        elif message.chat.type in {"group", "supergroup"}:
            replied = message.reply_to_message
            if replied is not None and replied.from_user is not None:
                preview = await attack_service.preview_by_telegram_id(
                    session,
                    attacker_telegram_id=message.from_user.id,
                    target_telegram_id=replied.from_user.id,
                    teacher_name=arguments,
                )
            else:
                parts = arguments.split(maxsplit=1)
                if len(parts) != 2:
                    await message.answer(
                        "فرمت حمله در گروه درست نیست.\n\n"
                        + _attack_help_text(group=True)
                    )
                    return
                preview = await attack_service.preview_by_username(
                    session,
                    attacker_telegram_id=message.from_user.id,
                    target_username=parts[0],
                    teacher_name=parts[1],
                )
        else:
            parts = arguments.split(maxsplit=1)
            if len(parts) != 2:
                await message.answer(_attack_help_text())
                return
            preview = await attack_service.preview_by_username(
                session,
                attacker_telegram_id=message.from_user.id,
                target_username=parts[0],
                teacher_name=parts[1],
            )
    except SchoolError as error:
        await _report_error(message, error)
        return
    if random_selection is not None:
        text = _random_attack_preview_content(random_selection)
        keyboard = _random_attack_confirmation_keyboard(
            random_selection, source_message_id=message.message_id
        )
    else:
        text = _preview_content(preview)
        keyboard = _attack_confirmation_keyboard(
            preview, source_message_id=message.message_id
        )
    if message.chat.type in {"group", "supergroup"}:
        await message.answer(
            text,
            reply_markup=keyboard,
            reply_to_message_id=message.message_id,
            parse_mode=MARKDOWN_V2,
        )
    else:
        await message.answer(
            text,
            reply_markup=keyboard,
            parse_mode=MARKDOWN_V2,
        )


@router.callback_query(RandomAttackCallback.filter())
async def random_attack_confirmation(
    callback, callback_data: RandomAttackCallback, session: AsyncSession
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    if callback.from_user.id != callback_data.attacker_id:
        await callback.answer(
            "فقط شروع‌کننده حمله می‌تواند این انتخاب را تغییر دهد.",
            show_alert=True,
        )
        return
    if callback_data.action == "cancel":
        with suppress(TelegramAPIError):
            await callback.message.delete()
        await callback.answer("پیش‌نمایش بسته شد؛ حریف تا پایان مهلت ثابت می‌ماند.")
        return
    if callback_data.action == "reroll":
        await callback.answer()
        try:
            selection = await attack_service.reroll_random_preview(
                session,
                attacker_telegram_id=callback.from_user.id,
                version=callback_data.version,
            )
            # Commit the paid reroll before editing Telegram, so a transient
            # Bot API failure can never make the same stale button charge twice.
            await session.commit()
            text = _random_attack_preview_content(selection)
            await callback.message.edit_text(
                text,
                reply_markup=_random_attack_confirmation_keyboard(
                    selection,
                    source_message_id=callback_data.source_message_id,
                ),
                parse_mode=MARKDOWN_V2,
            )
        except SchoolError as error:
            await _report_error(callback.message, error)
        return

    # Acknowledge before the database transaction so Telegram does not expire
    # the button query while the attack is being scheduled.
    await callback.answer()
    try:
        launch = await attack_service.launch_random_attack(
            session,
            attacker_telegram_id=callback.from_user.id,
            version=callback_data.version,
            source_chat_id=_source_group_chat_id(callback.message),
        )
        await session.commit()
        with suppress(TelegramAPIError):
            await callback.message.delete()
        reply_parameters = (
            ReplyParameters(message_id=callback_data.source_message_id)
            if callback_data.source_message_id
            else None
        )
        for sticker in launch.teacher_stickers:
            try:
                await callback.message.answer_sticker(
                    sticker, reply_parameters=reply_parameters
                )
            except TelegramAPIError:
                continue
        await _send_launch_message(callback.message, launch, session, reply_parameters)
    except SchoolError as error:
        await _report_error(callback.message, error)


@router.callback_query(AttackConfirmationCallback.filter())
async def attack_confirmation(
    callback, callback_data: AttackConfirmationCallback, session: AsyncSession
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    if callback.from_user.id != callback_data.attacker_id:
        await callback.answer(
            "فقط شروع‌کننده حمله می‌تواند آن را تأیید کند.", show_alert=True
        )
        return
    if callback_data.decision == "cancel":
        await callback.message.delete()
        await callback.answer("حمله لغو شد.")
        return
    # Acknowledge before the database transaction so Telegram does not expire
    # the button query while the attack is being calculated.
    await callback.answer()
    try:
        teacher_ids = [
            int(value)
            for value in callback_data.teacher_ids.split(",")
            if value.strip()
        ] or [callback_data.teacher_id]
        launch = await attack_service.start_attack_by_ids(
            session,
            attacker_telegram_id=callback.from_user.id,
            target_id=callback_data.target_id,
            teacher_ids=teacher_ids,
            source_chat_id=_source_group_chat_id(callback.message),
        )
        # Attack creation is complete before Telegram cleanup/stickers/messages.
        await session.commit()
        with suppress(TelegramAPIError):
            await callback.message.delete()
        reply_parameters = (
            ReplyParameters(message_id=callback_data.source_message_id)
            if callback_data.source_message_id
            else None
        )
        for sticker in launch.teacher_stickers:
            try:
                await callback.message.answer_sticker(
                    sticker, reply_parameters=reply_parameters
                )
            except TelegramAPIError:
                # A missing or invalid optional sticker must not block an attack.
                continue
        await _send_launch_message(callback.message, launch, session, reply_parameters)
    except SchoolError as error:
        await _report_error(callback.message, error)
