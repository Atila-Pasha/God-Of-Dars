from contextlib import suppress
from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MessageEntity,
    ReplyParameters,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import AttackConfirmationCallback, RandomAttackCallback
from app.bot.custom_emojis import custom_emoji_entity
from app.bot.utils.attack import teacher_phrase
from app.bot.utils.telegram import schedule_message_deletion
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


def _teacher_icons(preview: AttackPreview) -> tuple[str, list[MessageEntity]]:
    """Render every selected teacher icon, including admin-configured premium emoji."""
    icons: list[str] = []
    entities: list[MessageEntity] = []
    for teacher_emoji in preview.teacher_emojis or (None,):
        if icons:
            icons.append(" ")
        offset = len("".join(icons).encode("utf-16-le")) // 2
        icon, entity = custom_emoji_entity(teacher_emoji, fallback="👨‍🏫")
        icons.append(icon)
        if entity is not None:
            entities.append(entity.model_copy(update={"offset": offset}))
    return "".join(icons), entities


def _preview_content(preview: AttackPreview) -> tuple[str, list[MessageEntity]]:
    teacher_icons, entities = _teacher_icons(preview)
    text = (
        f"{teacher_icons} پیش‌نمایش حمله با {teacher_phrase(preview.teacher_name)}\n\n"
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
    return text, entities


def _preview_text(preview: AttackPreview) -> str:
    return _preview_content(preview)[0]


def _attack_help_text(*, group: bool = False) -> str:
    if group:
        return (
            "⚔️ راهنمای حمله در گروه\n\n"
            "روی پیام هدف Reply بزن و یکی از این قالب‌ها را بفرست:\n"
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


def _random_attack_preview_content(
    selection: RandomAttackPreview,
) -> tuple[str, list[MessageEntity]]:
    remaining_seconds = max(
        0, int((selection.expires_at - datetime.now(UTC)).total_seconds())
    )
    remaining_minutes = max(1, (remaining_seconds + 59) // 60)
    text, entities = _preview_content(selection.preview)
    return (
        text.removesuffix("آیا حمله را تأیید می‌کنی؟")
        + "🎲 این حریف برای شما انتخاب شده است.\n"
        + f"🔒 انتخاب تا حدود {remaining_minutes} دقیقه ثابت می‌ماند.\n"
        + f"♻️ دیدن حریف دیگر: {selection.reroll_coin_cost} سکه\n\n"
        + "حمله را تأیید می‌کنی یا حریف دیگری می‌خواهی؟",
        entities,
    )


def _random_attack_preview_text(selection: RandomAttackPreview) -> str:
    return _random_attack_preview_content(selection)[0]


def _random_attack_confirmation_keyboard(
    selection: RandomAttackPreview, *, source_message_id: int
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تأیید حمله",
                    callback_data=RandomAttackCallback(
                        action="confirm",
                        attacker_id=selection.preview.attacker_id,
                        version=selection.version,
                        source_message_id=source_message_id,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="❌ لغو",
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


async def _send_result(message: Message, result: AttackResult) -> None:
    await message.answer(_attack_text(result))
    bot = message.bot
    if bot is not None:
        with suppress(TelegramAPIError):
            await bot.send_message(
                result.target_telegram_id,
                f"🎯 شما مورد حمله قرار گرفتید!\n\n{_attack_text(result)}",
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
    elif isinstance(error, ShieldAlreadyActive):
        await message.answer(
            "🛡 این بازیکن سپر فعال دارد و فعلاً نمی‌توان به او حمله کرد."
        )
    elif isinstance(error, InvalidTeacherState):
        await message.answer(
            "این دبیر فعال نیست؛ ابتدا آن را فعال کنید تا آماده حمله شود."
        )
    elif isinstance(error, CannotAttackSelf):
        await message.answer("نمی‌توانید به خودتان حمله کنید.")
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


@router.message(F.text.regexp(r"^\s*حمله(?:\s+\S.*)?$"))
async def attack_message(message: Message, session: AsyncSession) -> None:
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
        await message.answer(
            "نام دبیر را هم بنویسید؛ مثال: حمله افلاطون",
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
        text, entities = _random_attack_preview_content(random_selection)
        keyboard = _random_attack_confirmation_keyboard(
            random_selection, source_message_id=message.message_id
        )
    else:
        text, entities = _preview_content(preview)
        keyboard = _attack_confirmation_keyboard(
            preview, source_message_id=message.message_id
        )
    if message.chat.type in {"group", "supergroup"}:
        await message.answer(
            text,
            reply_markup=keyboard,
            reply_to_message_id=message.message_id,
            entities=entities,
        )
    else:
        await message.answer(
            text,
            reply_markup=keyboard,
            entities=entities,
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
            text, entities = _random_attack_preview_content(selection)
            await callback.message.edit_text(
                text,
                reply_markup=_random_attack_confirmation_keyboard(
                    selection,
                    source_message_id=callback_data.source_message_id,
                ),
                entities=entities,
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
        launch_message = await callback.message.answer(
            f"⚔️ حمله به «{launch.target_name}» آغاز شد!\n"
            f"👨‍🏫 {teacher_phrase(launch.teacher_name)}\n"
            "⏱ زمان حمله: ۲ دقیقه\n"
            "پس از پایان زمان، نتیجه حمله برای شما ارسال می‌شود.",
            reply_parameters=reply_parameters,
        )
        schedule_message_deletion(launch_message, delay_seconds=10)
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
        launch_message = await callback.message.answer(
            f"⚔️ حمله به «{launch.target_name}» آغاز شد!\n"
            f"👨‍🏫 {teacher_phrase(launch.teacher_name)}\n"
            "⏱ زمان حمله: ۲ دقیقه\n"
            "پس از پایان زمان، نتیجه حمله برای شما ارسال می‌شود.",
            reply_parameters=reply_parameters,
        )
        schedule_message_deletion(launch_message, delay_seconds=10)
    except SchoolError as error:
        await _report_error(callback.message, error)
