from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import AttackConfirmationCallback
from app.bot.utils.attack import teacher_phrase
from app.services.attack_service import AttackPreview, AttackResult, AttackService
from app.services.school_errors import (
    AttackInProgress,
    InvalidTeacherState,
    SchoolError,
    SchoolUserNotFound,
    TeacherInHospital,
    TeacherNotOwned,
)

router = Router(name="battle")
attack_service = AttackService()


def _attack_text(result: AttackResult) -> str:
    teacher_state = (
        f"🩹 آسیب دبیر: {result.teacher_injury}"
        if result.teacher_injury
        else "🛡 دژ نتوانست به دبیر آسیب بزند."
    )
    return (
        f"⚔️ بازیکن «{result.attacker_name}» با {teacher_phrase(result.teacher_name)} "
        f"به دژ «{result.target_name}» حمله کرد!\n\n"
        f"✨ توانایی دبیر: {result.ability_text or 'بدون توانایی ثبت‌شده'}\n"
        f"💥 تخریب دژ: {result.castle_damage}\n"
        f"🏰 قدرت باقی‌مانده دژ: {result.castle_strength_after}\n"
        f"{teacher_state}\n"
        f"🎁 غنیمت: 🪙 {result.loot_coin}  💎 {result.loot_diamond}  🍌 موز {result.loot_banana}"
    )


def _preview_text(preview: AttackPreview) -> str:
    return (
        f"⚔️ پیش‌نمایش حمله با {teacher_phrase(preview.teacher_name)}\n\n"
        f"🎯 هدف: {preview.target_name}\n"
        f"⚔️ قدرت حمله دبیر: {preview.teacher_damage}\n"
        f"✨ توانایی دبیر: {preview.ability_text or 'بدون توانایی ثبت‌شده'}\n"
        f"🛡 دفاع دژ: {preview.defense_power}\n"
        f"💥 تخریب احتمالی دژ: {preview.estimated_castle_damage}\n"
        f"🩹 آسیب احتمالی دبیر: {preview.estimated_teacher_injury}\n\n"
        "🎁 غنیمت احتمالی از منابع حریف:\n"
        f"🪙 سکه: {preview.loot_coin}\n"
        f"💎 الماس: {preview.loot_diamond}\n"
        f"🍌 موز: {preview.loot_banana}\n\n"
        "آیا حمله را تأیید می‌کنی؟"
    )


def _attack_help_text(*, group: bool = False) -> str:
    if group:
        return (
            "⚔️ راهنمای حمله در گروه\n\n"
            "روی پیام هدف Reply بزن و یکی از این قالب‌ها را بفرست:\n"
            "• حمله {اسم دبیر}\n\n"
            "اگر روی پیام هدف Reply نزنی:\n"
            "• حمله {نام‌کاربری هدف} {اسم دبیر}"
        )
    return (
        "⚔️ راهنمای حمله در گفت‌وگوی خصوصی\n\n"
        "حمله {نام‌کاربری هدف} {اسم دبیر}\n"
        "مثال: حمله @player افلاطون\n\n"
        "در گروه، روی پیام هدف Reply بزن و بنویس:\n"
        "حمله {اسم دبیر}"
    )


def _attack_confirmation_keyboard(preview: AttackPreview) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ تأیید حمله",
            callback_data=AttackConfirmationCallback(
                attacker_id=preview.attacker_id,
                target_id=preview.target_id, teacher_id=preview.teacher_id,
                decision="confirm", teacher_ids=preview.teacher_ids,
            ).pack(),
        ),
        InlineKeyboardButton(
            text="❌ لغو",
            callback_data=AttackConfirmationCallback(
                attacker_id=preview.attacker_id,
                target_id=preview.target_id, teacher_id=preview.teacher_id,
                decision="cancel", teacher_ids=preview.teacher_ids,
            ).pack(),
        ),
    ]])


async def _send_result(message: Message, result: AttackResult) -> None:
    await message.answer(_attack_text(result))
    with suppress(TelegramAPIError):
        await message.bot.send_message(
            result.target_telegram_id,
            f"🎯 شما مورد حمله قرار گرفتید!\n\n{_attack_text(result)}",
        )


async def _report_error(message: Message, error: Exception) -> None:
    if isinstance(error, SchoolUserNotFound):
        await message.answer("بازیکن هدف پیدا نشد یا هنوز در ربات ثبت‌نام نکرده است.")
    elif isinstance(error, TeacherNotOwned):
        await message.answer("استادی با این نام پیدا نشد.")
    elif isinstance(error, TeacherInHospital):
        await message.answer("این استاد در حال بهبود است و فعلاً نمی‌تواند حمله کند.")
    elif isinstance(error, AttackInProgress):
        await message.answer("⚔️ حمله فعال دارید؛ پس از پایان آن می‌توانید دوباره حمله کنید.")
    elif isinstance(error, InvalidTeacherState):
        await message.answer("این استاد در بیمارستان است و فعلاً نمی‌تواند حمله کند.")
    else:
        await message.answer("اجرای حمله ممکن نبود؛ لطفاً مشخصات حمله را بررسی کنید.")


@router.message(Command("attack"))
async def attack_help_handler(message: Message) -> None:
    await message.answer(
        _attack_help_text(group=message.chat.type in {"group", "supergroup"})
    )


@router.message(F.text.regexp(r"^\s*حمله(?:\s+\S.*)?$"))
async def attack_message(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    text = (message.text or "").strip()
    arguments = text.partition(" ")[2].strip()
    if not arguments:
        await message.answer(
            _attack_help_text(
                group=message.chat.type in {"group", "supergroup"}
            )
        )
        return
    try:
        if message.chat.type in {"group", "supergroup"}:
            replied = message.reply_to_message
            if replied is not None and replied.from_user is not None:
                if not arguments:
                    await message.answer(
                        "نام دبیر را هم بنویسید؛ مثال: حمله افلاطون\n\n"
                        + _attack_help_text(group=True),
                        reply_to_message_id=message.message_id,
                    )
                    return
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
    if message.chat.type in {"group", "supergroup"}:
        await message.answer(
            _preview_text(preview),
            reply_markup=_attack_confirmation_keyboard(preview),
            reply_to_message_id=message.message_id,
        )
    else:
        await message.answer(
            _preview_text(preview),
            reply_markup=_attack_confirmation_keyboard(preview),
        )


@router.callback_query(AttackConfirmationCallback.filter())
async def attack_confirmation(
    callback, callback_data: AttackConfirmationCallback, session: AsyncSession
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    if callback.from_user.id != callback_data.attacker_id:
        await callback.answer("فقط شروع‌کننده حمله می‌تواند آن را تأیید کند.", show_alert=True)
        return
    if callback_data.decision == "cancel":
        await callback.message.edit_reply_markup(reply_markup=None)
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
        )
        await callback.message.edit_reply_markup(reply_markup=None)
        for sticker in launch.teacher_stickers:
            try:
                await callback.message.answer_sticker(sticker)
            except TelegramAPIError:
                # A missing or invalid optional sticker must not block an attack.
                continue
        await callback.message.answer(
            f"⚔️ حمله به «{launch.target_name}» آغاز شد!\n"
            f"👨‍🏫 {teacher_phrase(launch.teacher_name)}\n"
            "⏱ زمان حمله: ۲ دقیقه\n"
            "پس از پایان زمان، نتیجه حمله برای شما ارسال می‌شود."
        )
    except SchoolError as error:
        await _report_error(callback.message, error)
