from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import AttackConfirmationCallback
from app.services.attack_service import AttackPreview, AttackResult, AttackService
from app.services.school_errors import (
    InvalidTeacherState,
    SchoolError,
    SchoolUserNotFound,
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
        f"⚔️ {result.attacker_name} با {result.teacher_name} به دژ {result.target_name} حمله کرد!\n\n"
        f"✨ توانایی دبیر: {result.ability_text or 'بدون توانایی ثبت‌شده'}\n"
        f"💥 تخریب دژ: {result.castle_damage}\n"
        f"🏰 قدرت باقی‌مانده دژ: {result.castle_strength_after}\n"
        f"{teacher_state}\n"
        f"🎁 غنیمت: 🪙 {result.loot_coin}  💎 {result.loot_diamond}  🍌 {result.loot_banana}"
    )


def _preview_text(preview: AttackPreview) -> str:
    return (
        f"⚔️ پیش‌نمایش حمله با {preview.teacher_name}\n\n"
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


def _attack_confirmation_keyboard(preview: AttackPreview) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ تأیید حمله",
            callback_data=AttackConfirmationCallback(
                attacker_id=preview.attacker_id,
                target_id=preview.target_id, teacher_id=preview.teacher_id,
                decision="confirm",
            ).pack(),
        ),
        InlineKeyboardButton(
            text="❌ لغو",
            callback_data=AttackConfirmationCallback(
                attacker_id=preview.attacker_id,
                target_id=preview.target_id, teacher_id=preview.teacher_id,
                decision="cancel",
            ).pack(),
        ),
    ]])


async def _send_result(message: Message, result: AttackResult) -> None:
    await message.answer(_attack_text(result))
    try:
        await message.bot.send_message(
            result.target_telegram_id,
            f"🎯 شما مورد حمله قرار گرفتید!\n\n{_attack_text(result)}",
        )
    except TelegramAPIError:
        # A target may have blocked the bot; the attack itself is already committed.
        pass


async def _report_error(message: Message, error: Exception) -> None:
    if isinstance(error, SchoolUserNotFound):
        await message.answer("بازیکن هدف پیدا نشد یا هنوز در ربات ثبت‌نام نکرده است.")
    elif isinstance(error, TeacherNotOwned):
        await message.answer("این دبیر در مدرسه شما وجود ندارد.")
    elif isinstance(error, InvalidTeacherState):
        await message.answer("این دبیر فعال نیست و فعلاً نمی‌تواند حمله کند.")
    else:
        await message.answer("اجرای حمله ممکن نبود؛ لطفاً مشخصات حمله را بررسی کنید.")


@router.message(F.text.regexp(r"^\s*حمله\s+\S.*$"))
async def attack_message(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    text = (message.text or "").strip()
    try:
        if message.chat.type in {"group", "supergroup"}:
            replied = message.reply_to_message
            if replied is None or replied.from_user is None:
                await message.answer("برای حمله باید روی پیام بازیکن هدف ریپلای کنید.")
                return
            preview = await attack_service.preview_by_telegram_id(
                session,
                attacker_telegram_id=message.from_user.id,
                target_telegram_id=replied.from_user.id,
                teacher_name=text.removeprefix("حمله").strip(),
            )
        else:
            parts = text.removeprefix("حمله").strip().split(maxsplit=1)
            if len(parts) != 2:
                await message.answer("فرمت صحیح: حمله {نام کاربری} {نام دبیر}")
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
    kwargs = {"reply_markup": _attack_confirmation_keyboard(preview)}
    if message.chat.type in {"group", "supergroup"}:
        kwargs["reply_to_message_id"] = message.message_id
    await message.answer(_preview_text(preview), **kwargs)


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
    try:
        result = await attack_service.attack_by_ids(
            session,
            attacker_telegram_id=callback.from_user.id,
            target_id=callback_data.target_id,
            teacher_id=callback_data.teacher_id,
        )
        await callback.message.edit_reply_markup(reply_markup=None)
        await _send_result(callback.message, result)
        await callback.answer("حمله انجام شد.")
    except SchoolError as error:
        await callback.answer("این حمله دیگر قابل اجرا نیست؛ دوباره پیش‌نمایش بگیر.", show_alert=True)
        await _report_error(callback.message, error)
