from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin import keyboards
from admin.states import (
    BroadcastStates,
    ChanceBoxStates,
    ChanceCardStates,
    ChannelStates,
    QuestionStates,
    ShieldStates,
    TeacherStates,
    UserStates,
)
from app.bot.callbacks_chance import ChanceBoxCallback, ChanceCardCallback
from app.bot.group_question_publisher import GroupQuestionPublisher
from app.bot.middlewares.subscription import invalidate_channels_cache
from app.bot.utils.telegram import safe_edit_reply_markup, safe_edit_text
from app.core.config import settings
from app.core.enums import ResourceType
from app.db.session import AsyncSessionLocal
from app.models.chance_box import ChanceBox
from app.models.user import User
from app.repositories.bot_settings import BotSettingsRepository
from app.repositories.group import GroupRepository
from app.repositories.user import UserRepository
from app.services.admin_service import AdminService
from app.services.chance_service import ChanceService
from app.services.library_errors import GroupNotFound
from app.services.question_service import QuestionService
from app.services.shield_service import ShieldAdminService

router = Router(name="admin")
service = AdminService()
question_service = QuestionService()
shield_service = ShieldAdminService()
bot_settings_repository = BotSettingsRepository()
group_repository = GroupRepository()
user_repository = UserRepository()
chance_service = ChanceService()
logger = logging.getLogger(__name__)
group_question_publisher = GroupQuestionPublisher()

TEACHER_EDIT_PROMPTS = {
    "name": "نام جدید دبیر را بفرستید:",
    "damage": "میزان آسیب جدید را بفرستید:",
    "max_hp": "حداکثر جان جدید را بفرستید:",
    "purchase_price": "قیمت خرید جدید را بفرستید:",
    "upgrade_price": "قیمت ارتقای جدید را بفرستید:",
    "unlock_level": "سطح بازشدن جدید را بفرستید:",
    "ability_text": "متن توانایی جدید را بفرستید؛ برای حذف، - بفرستید:",
    "sticker": "آیدی استیکر جدید را بفرستید؛ برای حذف، - بفرستید:",
    "emoji": "آیدی اموجی پرمیوم جدید را بفرستید؛ برای حذف، - بفرستید:",
}
SHIELD_EDIT_PROMPTS = {
    "name": "نام جدید سپر را بفرستید:",
    "reduction_percent": "درصد کاهش جدید را بفرستید (۰ تا ۱۰۰):",
    "flat_absorption": "مقدار جذب ثابت جدید را بفرستید:",
    "purchase_price": "قیمت خرید جدید را بفرستید:",
    "unlock_level": "سطح بازشدن جدید را بفرستید:",
    "description": "توضیح جدید را بفرستید؛ برای حذف، - بفرستید:",
}


def allowed(message: Message | CallbackQuery) -> bool:
    return (
        message.from_user is not None and message.from_user.id in settings.admin_id_set
    )


def number(value: str, label: str, *, minimum: int = 0) -> int:
    # Telegram admins often use Persian/Arabic digits or thousand separators.
    normalized = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬,",
        "01234567890123456789  ",
    )
    raw_value = value.strip().translate(normalized).replace(" ", "")
    if not re.fullmatch(r"\d+", raw_value):
        raise ValueError(f"{label} باید عدد صحیح باشد؛ فقط عدد وارد کنید.")
    try:
        result = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{label} باید عدد صحیح باشد؛ فقط عدد وارد کنید.") from exc
    if result < minimum:
        raise ValueError(f"{label} نمی‌تواند کمتر از {minimum} باشد.")
    return result


def _chance_values(value: str) -> tuple[ResourceType, int]:
    parts = value.replace("،", " ").split()
    if len(parts) != 2:
        raise ValueError("فرمت صحیح: طلا 100 یا الماس 5")
    resource = {"طلا": ResourceType.COIN, "سکه": ResourceType.COIN, "الماس": ResourceType.DIAMOND}.get(parts[0].casefold())
    if resource is None:
        raise ValueError("نوع جایزه فقط طلا یا الماس است.")
    return resource, number(parts[1], "مقدار", minimum=0)


async def _main_bot() -> Bot:
    return Bot(
        token=settings.BOT_TOKEN,
        session=AiohttpSession(
            proxy=settings.TELEGRAM_PROXY,
            limit=settings.TELEGRAM_HTTP_LIMIT,
        ),
    )


async def _expire_box_later(chat_id: int, message_id: int, box_id: int, expires_at: datetime) -> None:
    delay = max(0, (expires_at - datetime.now(UTC)).total_seconds())
    await asyncio.sleep(delay)
    async with AsyncSessionLocal() as cleanup_session:
        box = await cleanup_session.get(ChanceBox, box_id)
        if box is None or box.claimed_by_user_id is not None:
            return
        async with await _main_bot() as bot:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except TelegramAPIError:
                logger.info("Could not delete expired chance box message %s", message_id)
        await cleanup_session.delete(box)
        await cleanup_session.commit()


@router.message(F.text.in_({"ارسال جعبه شانس", "🎁 ارسال جعبه شانس"}))
async def chance_box_start(message: Message, state: FSMContext) -> None:
    if allowed(message):
        await state.set_state(ChanceBoxStates.section)
        await message.answer("جعبه برای کدام بخش ارسال شود؟", reply_markup=keyboards.chance_box_sections())


@router.message(ChanceBoxStates.section, F.text.regexp(r"^(?:📦\s*)?ارسال به بخش "))
async def chance_box_section(message: Message, state: FSMContext) -> None:
    if not allowed(message) or not message.text:
        return
    section = {"۱": 1, "۲": 2, "۳": 3, "۴": 4}.get(message.text[-1])
    if section is None:
        await message.answer("بخش نامعتبر است.")
        return
    await state.update_data(section=section)
    await state.set_state(ChanceBoxStates.value)
    await message.answer("پاداش جعبه را وارد کنید؛ نمونه: طلا 100 یا الماس 5")


@router.message(ChanceBoxStates.value)
async def chance_box_send(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not allowed(message) or not message.text:
        return
    try:
        resource, amount = _chance_values(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    groups = await group_repository.list_active(session)
    section = int((await state.get_data()).get("section", 1))
    # Telegram chat IDs provide a stable partition: removing/registering a
    # different group does not move existing groups between sections.
    groups = [
        group for group in groups
        if abs(group.telegram_chat_id) % 4 == section - 1
    ]
    sent = 0
    async with await _main_bot() as bot:
        for group in groups:
            # Persist first so the callback ID can be embedded in the message
            # itself; sending without a keyboard and editing afterwards is
            # racy and can leave a visible box with no button.
            box = await chance_service.create_box(group_id=group.id, session=session, message_id=0, resource=resource, amount=amount)
            sent_message = await bot.send_message(
                group.telegram_chat_id,
                f"🎁 جعبه شانس\n\nاولین نفری که جعبه را باز کند، {amount} {('طلا' if resource is ResourceType.COIN else 'الماس')} دریافت می‌کند!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🎁 باز کردن جعبه", callback_data=ChanceBoxCallback(box_id=box.id).pack())
                ]]),
            )
            box.telegram_message_id = sent_message.message_id
            await session.flush()
            asyncio.create_task(
                _expire_box_later(
                    group.telegram_chat_id,
                    sent_message.message_id,
                    box.id,
                    box.expires_at,
                )
            )
            sent += 1
    await state.clear()
    await message.answer(f"✅ جعبه به {sent} گروه فعال ارسال شد.", reply_markup=keyboards.main())


@router.message(F.text.in_({"ارسال کارت شانس", "🃏 ارسال کارت شانس"}))
async def chance_card_start(message: Message, state: FSMContext) -> None:
    if allowed(message):
        await state.set_state(ChanceCardStates.value)
        await message.answer("پاداش کارت همگانی را وارد کنید؛ نمونه: طلا 100 یا الماس 5")


@router.message(ChanceCardStates.target)
async def chance_card_target(message: Message, state: FSMContext) -> None:
    if not allowed(message) or not message.text:
        return
    try:
        target = number(message.text, "شناسه کاربر", minimum=1)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(target=target)
    await state.set_state(ChanceCardStates.value)
    await message.answer("پاداش کارت را وارد کنید؛ نمونه: طلا 100 یا الماس 5")


@router.message(ChanceCardStates.value)
async def chance_card_send(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not allowed(message) or not message.text:
        return
    try:
        resource, amount = _chance_values(message.text)
        sent = 0
        failed = 0
        last_user_id = 0
        batch_size = max(1, settings.BROADCAST_BATCH_SIZE)
        async with await _main_bot() as bot:
            while True:
                result = await session.execute(
                    select(User.id, User.telegram_user_id)
                    .where(User.is_active.is_(True), User.id > last_user_id)
                    .order_by(User.id)
                    .limit(batch_size)
                )
                users = result.all()
                if not users:
                    break
                for user_id, telegram_user_id in users:
                    answer, image, _ = chance_service.captcha()
                    card = await chance_service.create_card(
                        session, user_id, resource, amount, answer
                    )
                    try:
                        for attempt in range(2):
                            try:
                                await bot.send_photo(
                                    telegram_user_id,
                                    BufferedInputFile(image, filename="chance-captcha.png"),
                                    caption=f"🃏 کارت شانس\n\nکپچا را حل کن تا {amount} {('طلا' if resource is ResourceType.COIN else 'الماس')} بگیری.",
                                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                                        InlineKeyboardButton(text="✅ وارد کردن کپچا", callback_data=ChanceCardCallback(card_id=card.id).pack())
                                    ]]),
                                )
                                break
                            except TelegramRetryAfter as exc:
                                if attempt == 1:
                                    raise
                                await asyncio.sleep(exc.retry_after)
                        sent += 1
                    except TelegramAPIError as exc:
                        await session.delete(card)
                        await session.flush()
                        logger.warning(
                            "Could not send chance card %s to Telegram user %s: %s",
                            card.id,
                            telegram_user_id,
                            exc,
                        )
                        failed += 1
                    await asyncio.sleep(max(0, settings.TELEGRAM_SEND_DELAY))
                last_user_id = users[-1][0]
                # Do not keep every generated card in one transaction when the
                # audience is large. The next page starts after this key.
                await session.commit()
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await session.commit()
    await state.clear()
    await message.answer(f"✅ کارت شانس همگانی ارسال شد.\nموفق: {sent}\nناموفق: {failed}", reply_markup=keyboards.main())


@router.message(F.text.in_({"مدیریت قفل کانال", "📢 مدیریت قفل کانال"}))
async def channel_settings(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not allowed(message):
        return
    await state.clear()
    channels = await bot_settings_repository.list_channels(session)
    channel = "\n".join(
        f"{item.id}) {item.username or item.telegram_id}" for item in channels
    ) or "خاموش"
    await message.answer(
        f"📢 قفل کانال\n\nکانال فعلی: {channel}\n"
        "برای افزودن کانال، یوزرنیم (مثلاً @mychannel) یا شناسه عددی را بفرستید.\n"
        "برای حذف، «حذف شماره» مثل «حذف 2» را بفرستید.",
        reply_markup=keyboards.main(),
    )
    await state.set_state(ChannelStates.value)


@router.message(Command("channel_add"))
async def channel_add_command(message: Message, state: FSMContext) -> None:
    if allowed(message):
        await state.set_state(ChannelStates.value)
        await message.answer("یوزرنیم یا شناسه عددی کانال را بفرستید:")


@router.message(Command("channel_remove"))
async def channel_remove_command(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if allowed(message):
        await bot_settings_repository.clear_channel(session)
        await session.commit()
        invalidate_channels_cache()
        await state.clear()
        await message.answer("✅ قفل کانال حذف شد.", reply_markup=keyboards.main())


@router.message(ChannelStates.value)
async def channel_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not allowed(message) or not message.text:
        return
    value = message.text.strip()
    if value.casefold() in {"حذف", "delete", "off", "خاموش"}:
        # Old singleton values are also cleared for a complete off switch.
        await bot_settings_repository.clear_channel(session)
        await session.commit()
        invalidate_channels_cache()
        result = "قفل کانال حذف شد."
    elif value.casefold().startswith(("حذف ", "delete ")):
        try:
            channel_id = int(value.split(maxsplit=1)[1])
        except (IndexError, ValueError):
            await message.answer("فرمت حذف صحیح نیست؛ نمونه: حذف 2")
            return
        removed = await bot_settings_repository.remove_channel(session, channel_id)
        if removed:
            await session.commit()
            invalidate_channels_cache()
        result = "کانال حذف شد." if removed else "کانال پیدا نشد."
    else:
        await bot_settings_repository.add_channel(session, value)
        await session.commit()
        invalidate_channels_cache()
        result = f"کانال {value} به قفل‌ها اضافه شد."
    await state.clear()
    await message.answer("✅ " + result, reply_markup=keyboards.main())


def user_text(user) -> str:
    name = " ".join(x for x in (user.first_name, user.last_name) if x)
    r = user.resources
    return (
        f"👤 {name or 'بدون نام'}\n🆔 شناسه داخلی: {user.id}\n"
        f"📱 تلگرام: {user.telegram_user_id}\n🔗 نام کاربری: @{user.username or 'ندارد'}\n"
        f"وضعیت: {'فعال' if user.is_active else 'مسدود'}\n"
        f"منابع: 🪙 {r.coin if r else 0} | 💎 {r.diamond if r else 0} | ✨ XP {r.banana if r else 0}"
    )


def user_teachers_text(user, teachers) -> str:
    if not teachers:
        return f"👨‍🏫 دبیرهای کاربر «{user.first_name}»\n\nاین کاربر دبیری ندارد."
    lines = [f"👨‍🏫 دبیرهای کاربر «{user.first_name}»\n"]
    for item in teachers:
        teacher = item.teacher
        lines.append(
            f"#{item.id} — {teacher.name}\n"
            f"سطح: {item.level} | جان: {item.current_hp}/{teacher.max_hp}\n"
            f"وضعیت: {item.status.value}"
        )
    return "\n\n".join(lines)


@router.message(CommandStart())
@router.message(Command("admin"))
async def start(message: Message, state: FSMContext) -> None:
    if not allowed(message):
        return
    await state.clear()
    await message.answer("پنل مدیریت آماده است.", reply_markup=keyboards.main())


@router.message(F.text.in_({"لغو", "❌ لغو"}))
async def cancel(message: Message, state: FSMContext) -> None:
    if allowed(message):
        await state.clear()
        await message.answer("لغو شد.", reply_markup=keyboards.main())


@router.message(F.text.in_({"پیام همگانی", "📣 پیام همگانی"}))
async def broadcast_start(message: Message, state: FSMContext) -> None:
    if allowed(message):
        await state.clear()
        await state.set_state(BroadcastStates.content)
        await message.answer(
            "پیام همگانی را بفرستید.\nمی‌توانید فقط متن، یا عکس همراه کپشن ارسال کنید."
        )


@router.message(BroadcastStates.content)
async def broadcast_send(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    if not allowed(message):
        return
    if not message.text and not message.photo:
        await message.answer("فقط پیام متنی یا عکس همراه کپشن قابل ارسال است.")
        return

    total_recipients = await session.scalar(select(func.count(User.id)))
    if not total_recipients:
        await state.clear()
        await message.answer(
            "هیچ کاربری برای ارسال پیام وجود ندارد.", reply_markup=keyboards.main()
        )
        return

    await state.clear()
    # Release the database connection before the potentially long Telegram
    # broadcast. Recipient IDs are fetched page-by-page below.
    await session.commit()
    await message.answer(
        f"📣 ارسال پیام برای {total_recipients} کاربر شروع شد؛ لطفاً صبر کنید...",
        reply_markup=keyboards.main(),
    )

    main_session = AiohttpSession(
        proxy=settings.TELEGRAM_PROXY,
        limit=settings.TELEGRAM_HTTP_LIMIT,
    )
    sent = 0
    failed = 0
    async with Bot(token=settings.BOT_TOKEN, session=main_session) as main_bot:
        photo_file: BufferedInputFile | None = None
        if message.photo:
            buffer = BytesIO()
            await message.bot.download(message.photo[-1].file_id, destination=buffer)
            photo_file = BufferedInputFile(buffer.getvalue(), filename="broadcast.jpg")

        last_user_id = 0
        batch_size = max(1, settings.BROADCAST_BATCH_SIZE)
        while True:
            result = await session.execute(
                select(User.id, User.telegram_user_id)
                .where(User.id > last_user_id)
                .order_by(User.id)
                .limit(batch_size)
            )
            recipients = result.all()
            if not recipients:
                break
            await session.commit()
            for user_id, telegram_user_id in recipients:
                try:
                    for attempt in range(2):
                        try:
                            if photo_file is not None:
                                # A new BufferedInputFile is needed because the
                                # Telegram client consumes the file stream during
                                # each upload.
                                await main_bot.send_photo(
                                    chat_id=telegram_user_id,
                                    photo=BufferedInputFile(
                                        photo_file.data, filename="broadcast.jpg"
                                    ),
                                    caption=message.caption,
                                )
                            else:
                                await main_bot.send_message(
                                    chat_id=telegram_user_id,
                                    text=message.text,
                                )
                            break
                        except TelegramRetryAfter as exc:
                            if attempt == 1:
                                raise
                            await asyncio.sleep(exc.retry_after)
                    sent += 1
                except TelegramAPIError:
                    failed += 1
                await asyncio.sleep(max(0, settings.TELEGRAM_SEND_DELAY))
            last_user_id = recipients[-1][0]
        await session.commit()

    await message.answer(
        f"✅ پیام همگانی تمام شد.\nموفق: {sent}\nناموفق: {failed}",
        reply_markup=keyboards.main(),
    )


@router.message(F.text.in_({"مدیریت کاربران", "👤 مدیریت کاربران"}))
async def users(message: Message, state: FSMContext) -> None:
    if allowed(message):
        await state.set_state(UserStates.search)
        await message.answer(
            "شناسه تلگرام، شناسه داخلی یا نام کاربری کاربر را بفرستید:"
        )


@router.message(UserStates.search)
async def user_search(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    if not allowed(message) or not message.text:
        return
    found = await service.find_users(session, message.text)
    if not found:
        await message.answer("کاربری پیدا نشد. دوباره جستجو کنید یا لغو بزنید.")
        return
    await state.clear()
    for user in found:
        await message.answer(
            user_text(user),
            reply_markup=keyboards.user_actions(user.id, user.is_active),
        )


@router.callback_query(F.data.startswith("user:"))
async def user_callback(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    if not allowed(callback) or not callback.data:
        return
    _, action, raw_id = callback.data.split(":")
    user_id = int(raw_id)
    user = await service.get_user(session, user_id)
    if user is None:
        await callback.answer("کاربر پیدا نشد.", show_alert=True)
        return
    if action == "toggle":
        user = await service.set_user_active(session, user_id, not user.is_active)
        await safe_edit_text(
            callback.message,
            user_text(user),
            reply_markup=keyboards.user_actions(user.id, user.is_active),
        )
        await callback.answer("وضعیت تغییر کرد.")
        return
    if action == "teachers":
        teachers = await service.list_user_teachers(session, user_id)
        await callback.message.answer(
            user_teachers_text(user, teachers),
            reply_markup=keyboards.user_teacher_list(user_id, teachers),
        )
        await callback.answer()
        return
    await state.update_data(user_id=user_id)
    await state.set_state(UserStates.resource_coin)
    await callback.message.answer("چقدر سکه اضافه کنم؟\nبرای صفر، 0 بفرستید.")
    await callback.answer()


@router.callback_query(F.data.startswith("user_teacher:"))
async def user_teacher_callback(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    if not allowed(callback) or not callback.data:
        return
    parts = callback.data.split(":")
    if (
        parts[1] == "close"
        and len(parts) == 3
    ):
        await callback.message.delete()
        await callback.answer()
        return
    if len(parts) != 4 or parts[1] != "delete":
        await callback.answer("عملیات نامعتبر است.", show_alert=True)
        return
    user_id = int(parts[2])
    user_teacher_id = int(parts[3])
    user_teacher = await service.delete_user_teacher(
        session, user_teacher_id, user_id
    )
    if user_teacher is None:
        await callback.answer("این دبیر برای کاربر پیدا نشد.", show_alert=True)
        return
    user = await service.get_user(session, user_id)
    if user is None:
        await callback.answer("کاربر پیدا نشد.", show_alert=True)
        return
    teachers = await service.list_user_teachers(session, user_id)
    await safe_edit_text(
        callback.message,
        user_teachers_text(user, teachers),
        reply_markup=keyboards.user_teacher_list(user_id, teachers),
    )
    await callback.answer(f"دبیر «{user_teacher.teacher.name}» حذف شد.")


@router.message(UserStates.resource_coin)
async def resource_coin(message: Message, state: FSMContext) -> None:
    if not allowed(message) or not message.text:
        return
    try:
        value = number(message.text, "مقدار سکه")
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(coin=value)
    await state.set_state(UserStates.resource_diamond)
    await message.answer("چقدر الماس اضافه کنم؟\nبرای صفر، 0 بفرستید.")


@router.message(UserStates.resource_diamond)
async def resource_diamond(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    if not allowed(message) or not message.text:
        return
    try:
        value = number(message.text, "مقدار الماس")
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(diamond=value)
    await save_resources(message, state, session)


@router.message(UserStates.resource_banana)
async def save_resources(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    if not allowed(message) or not message.text:
        return
    data = await state.get_data()
    user = await service.add_resources(
        session,
        data["user_id"],
        coin=data["coin"],
        diamond=data["diamond"],
        banana=0,
    )
    await state.clear()
    if user is None:
        await message.answer("کاربر پیدا نشد.", reply_markup=keyboards.main())
        return
    amounts = f"🪙 {data['coin']} سکه و 💎 {data['diamond']} الماس"
    await message.answer(
        "منابع با موفقیت اضافه شد.\n" + user_text(user), reply_markup=keyboards.main()
    )
    try:
        main_session = (
            AiohttpSession(
                proxy=settings.TELEGRAM_PROXY,
                limit=settings.TELEGRAM_HTTP_LIMIT,
            )
        )
        async with Bot(token=settings.BOT_TOKEN, session=main_session) as main_bot:
            await main_bot.send_message(
                chat_id=user.telegram_user_id,
                text=f"🎁 شما {amounts} از طرف مدیریت دریافت کردید.",
            )
    except TelegramAPIError:
        # The grant is already valid; an unavailable/blocked chat must not
        # roll back the database operation.
        await message.answer("منابع اضافه شد، اما ارسال اعلان برای کاربر ممکن نبود.")


@router.message(F.text.in_({"ساخت سؤال روزانه", "❓ ساخت سؤال روزانه"}))
async def question_start(message: Message, state: FSMContext) -> None:
    if allowed(message):
        await state.clear()
        await state.update_data(scope="daily")
        await state.set_state(QuestionStates.text)
        await message.answer("متن سؤال روزانه را بفرستید:")


@router.message(F.text.in_({"ساخت سؤال گروهی", "👥 ساخت سؤال گروهی"}))
async def group_question_start(message: Message, state: FSMContext) -> None:
    if allowed(message):
        await state.clear()
        await state.update_data(scope="group")
        await state.set_state(QuestionStates.text)
        await message.answer("متن سؤال گروهی را بفرستید:")


async def question_step(
    message: Message, state: FSMContext, next_state, key: str, prompt: str
) -> None:
    if not allowed(message) or not message.text:
        return
    await state.update_data(**{key: message.text.strip()})
    await state.set_state(next_state)
    await message.answer(prompt)


@router.message(QuestionStates.text)
async def q_text(message, state):
    await question_step(
        message, state, QuestionStates.answer, "text", "پاسخ صحیح را بفرستید:"
    )


@router.message(QuestionStates.answer)
async def q_answer(message, state):
    await question_step(
        message, state, QuestionStates.hours, "answer", "مدت اعتبار به ساعت (مثلاً 24):"
    )


async def q_number(
    message: Message,
    state: FSMContext,
    next_state,
    key: str,
    prompt: str,
    default: int = 0,
) -> None:
    if not allowed(message) or not message.text:
        return
    try:
        value = (
            default if message.text.strip() == "-" else number(message.text, "مقدار")
        )
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(**{key: value})
    await state.set_state(next_state)
    await message.answer(prompt)


@router.message(QuestionStates.hours)
async def q_hours(message: Message, state: FSMContext) -> None:
    if not allowed(message) or not message.text:
        return
    try:
        hours = number(message.text, "مدت اعتبار", minimum=1)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(hours=hours)
    await state.set_state(QuestionStates.coin)
    await message.answer("پاداش سکه را فقط به‌صورت عدد بفرستید (برای صفر: 0):")


@router.message(QuestionStates.coin)
async def q_coin(message, state):
    await q_number(
        message,
        state,
        QuestionStates.diamond,
        "coin",
        "پاداش الماس را فقط به‌صورت عدد بفرستید (برای صفر: 0):",
    )


@router.message(QuestionStates.diamond)
async def q_diamond(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not allowed(message) or not message.text:
        return
    try:
        value = 0 if message.text.strip() == "-" else number(message.text, "مقدار")
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(diamond=value, banana=0)
    await q_banana(message, state, session)


@router.message(QuestionStates.banana)
async def q_banana(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not allowed(message) or not message.text:
        return
    banana = 0
    data = await state.get_data()
    expires_at = datetime.now(UTC) + timedelta(hours=data["hours"])
    if data.get("scope") == "group":
        main_session = (
            AiohttpSession(
                proxy=settings.TELEGRAM_PROXY,
                limit=settings.TELEGRAM_HTTP_LIMIT,
            )
        )
        try:
            async with Bot(token=settings.BOT_TOKEN, session=main_session) as main_bot:
                result = await group_question_publisher.create_and_publish(
                    main_bot,
                    session,
                    question_text=data["text"],
                    correct_answer=data["answer"],
                    expires_at=expires_at,
                    coin_reward=data["coin"],
                    diamond_reward=data["diamond"],
                    banana_reward=banana,
                )
        except GroupNotFound:
            await state.clear()
            await message.answer(
                "هیچ گروه فعال و ثبت‌شده‌ای برای ارسال سؤال وجود ندارد.",
                reply_markup=keyboards.main(),
            )
            return
        await state.clear()
        await message.answer(
            f"✅ سؤال گروهی ساخته و ارسال شد.\nشناسه: {result.question.id}\n"
            f"گروه‌های موفق: {len(result.sent_chat_ids)}\nگروه‌های ناموفق: {len(result.failed_chat_ids)}",
            reply_markup=keyboards.main(),
        )
        return

    question = await question_service.create_daily_question(
        session,
        question_text=data["text"],
        correct_answer=data["answer"],
        expires_at=expires_at,
        coin_reward=data["coin"],
        diamond_reward=data["diamond"],
        banana_reward=banana,
    )
    await state.clear()
    await message.answer(
        f"✅ سؤال روزانه ساخته شد. شناسه: {question.id}", reply_markup=keyboards.main()
    )


@router.message(F.text.in_({"مدیریت دبیرها", "👨‍🏫 مدیریت دبیرها"}))
async def teachers(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not allowed(message):
        return
    await state.clear()
    items = await service.list_teachers(session)
    if not items:
        await message.answer("هنوز دبیرهی ثبت نشده است.")
    for teacher in items:
        await message.answer(
            f"👨‍🏫 {teacher.name}\nشناسه: {teacher.id}\nآسیب: {teacher.damage} | جان: {teacher.max_hp}\n"
            f"خرید: {teacher.purchase_price} سکه | ارتقا: {teacher.upgrade_price} الماس\n"
            f"بازشدن در سطح: {teacher.unlock_level}\n"
            f"توانایی: {teacher.ability_text or '—'}\n"
            f"استیکر: {teacher.sticker or '—'} | اموجی: {teacher.emoji or '—'}\n"
            f"وضعیت: {'فعال' if teacher.is_active else 'غیرفعال'}",
            reply_markup=keyboards.teacher_actions(teacher.id),
        )
    await message.answer(
        "برای ساخت دبیر جدید، /teacher را بفرستید.", reply_markup=keyboards.main()
    )


@router.message(Command("teacher"))
async def teacher_start(message: Message, state: FSMContext) -> None:
    if allowed(message):
        await state.clear()
        await state.update_data(mode="create")
        await state.set_state(TeacherStates.name)
        await message.answer("نام دبیر:")


async def teacher_value(
    message: Message,
    state: FSMContext,
    key: str,
    next_state,
    prompt: str,
    *,
    numeric: bool = True,
) -> None:
    if not allowed(message) or not message.text:
        return
    value = message.text.strip()
    if numeric:
        try:
            value = number(value, key)
        except ValueError as exc:
            await message.answer(str(exc))
            return
    await state.update_data(**{key: value})
    await state.set_state(next_state)
    await message.answer(prompt)


@router.message(TeacherStates.name)
async def t_name(message, state):
    await teacher_value(
        message, state, "name", TeacherStates.damage, "میزان آسیب:", numeric=False
    )


@router.message(TeacherStates.damage)
async def t_damage(message, state):
    await teacher_value(message, state, "damage", TeacherStates.max_hp, "حداکثر جان:")


@router.message(TeacherStates.max_hp)
async def t_hp(message, state):
    await teacher_value(
        message, state, "max_hp", TeacherStates.purchase_price, "قیمت خرید:"
    )


@router.message(TeacherStates.purchase_price)
async def t_buy(message, state):
    await teacher_value(
        message, state, "purchase_price", TeacherStates.upgrade_price, "قیمت ارتقا:"
    )


@router.message(TeacherStates.upgrade_price)
async def t_upgrade(message, state):
    await teacher_value(
        message, state, "upgrade_price", TeacherStates.unlock_level, "سطح بازشدن:"
    )


@router.message(TeacherStates.unlock_level)
async def t_unlock(message, state):
    await teacher_value(
        message,
        state,
        "unlock_level",
        TeacherStates.ability_text,
        "متن توانایی (برای خالی بودن - بفرستید):",
    )


@router.message(TeacherStates.ability_text)
async def t_ability(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not allowed(message) or not message.text:
        return
    await state.update_data(
        ability_text=None if message.text.strip() == "-" else message.text.strip()
    )
    await state.set_state(TeacherStates.sticker)
    await message.answer("آیدی استیکر دبیر را وارد کنید (برای خالی بودن - بفرستید):")


@router.message(TeacherStates.sticker)
async def t_sticker(message: Message, state: FSMContext) -> None:
    if not allowed(message) or not message.text:
        return
    value = message.text.strip()
    await state.update_data(sticker=None if value == "-" else value)
    await state.set_state(TeacherStates.emoji)
    await message.answer("آیدی اموجی دبیر را وارد کنید (برای خالی بودن - بفرستید):")


@router.message(TeacherStates.emoji)
async def t_emoji(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not allowed(message) or not message.text:
        return
    data = await state.get_data()
    data["emoji"] = None if message.text.strip() == "-" else message.text.strip()
    mode = data.pop("mode", "create")
    teacher_id = data.pop("teacher_id", None)
    teacher = (
        await service.update_teacher(session, teacher_id, **data)
        if mode == "edit"
        else await service.create_teacher(session, **data)
    )
    await state.clear()
    await message.answer(
        f"✅ دبیر «{teacher.name}» با شناسه {teacher.id} {'ویرایش شد' if mode == 'edit' else 'ساخته شد'}.",
        reply_markup=keyboards.main(),
    )


@router.callback_query(F.data.startswith("teacher:"))
async def teacher_callback(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    if not allowed(callback) or not callback.data:
        return
    parts = callback.data.split(":")
    if len(parts) < 3 or parts[0] != "teacher":
        await callback.answer("دکمه منقضی یا نامعتبر است.", show_alert=True)
        return
    action = parts[1]
    raw_id = parts[2]
    try:
        teacher_id = int(raw_id)
    except ValueError:
        await callback.answer("شناسه دبیر نامعتبر است.", show_alert=True)
        return
    teacher = await service.get_teacher(session, teacher_id)
    if teacher is None:
        await callback.answer("دبیر پیدا نشد.", show_alert=True)
        return
    if action == "delete":
        deleted, teacher = await service.delete_teacher(session, teacher_id)
        await callback.answer(
            "حذف شد." if deleted else "این دبیر استفاده شده؛ غیرفعال شد.",
            show_alert=True,
        )
        await safe_edit_reply_markup(callback.message, reply_markup=None)
        return
    if action == "edit":
        await state.clear()
        await callback.message.answer(
            f"ویرایش دبیر «{teacher.name}»\nیک مورد را برای تغییر انتخاب کنید:",
            reply_markup=keyboards.teacher_edit_fields(teacher_id),
        )
    elif action == "field" and len(parts) == 4:
        field = parts[3]
        if field not in TEACHER_EDIT_PROMPTS:
            await callback.answer("این گزینه معتبر نیست.", show_alert=True)
            return
        await state.clear()
        await state.update_data(edit_id=teacher_id, edit_field=field)
        await state.set_state(TeacherStates.edit_value)
        await callback.message.answer(
            TEACHER_EDIT_PROMPTS[field], reply_markup=keyboards.cancel_keyboard()
        )
    elif action == "done":
        await state.clear()
        await callback.message.answer(
            f"ویرایش دبیر «{teacher.name}» تمام شد.", reply_markup=keyboards.main()
        )
    else:
        await callback.answer("عملیات ویرایش معتبر نیست.", show_alert=True)
        return
    await callback.answer()


@router.message(TeacherStates.edit_value)
async def teacher_edit_value(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    if not allowed(message) or not message.text:
        return
    data = await state.get_data()
    field = data.get("edit_field")
    teacher_id = data.get("edit_id")
    if field not in TEACHER_EDIT_PROMPTS or teacher_id is None:
        await state.clear()
        await message.answer("فلو ویرایش منقضی شد.", reply_markup=keyboards.main())
        return
    value = message.text.strip()
    try:
        if field in {"name"}:
            if not value:
                raise ValueError("نام دبیر نمی‌تواند خالی باشد.")
        elif field in {"ability_text", "sticker", "emoji"}:
            value = None if value == "-" else value
        else:
            value = number(value, field, minimum=1 if field == "unlock_level" else 0)
            if field == "reduction_percent" and value > 100:
                raise ValueError("درصد کاهش آسیب نمی‌تواند بیشتر از 100 باشد.")
        teacher = await service.update_teacher(session, int(teacher_id), **{field: value})
        if teacher is None:
            raise ValueError("دبیر پیدا نشد.")
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=keyboards.cancel_keyboard())
        return
    await state.clear()
    await message.answer("تغییر ذخیره شد.", reply_markup=keyboards.main())
    await message.answer(
        f"ویرایش دبیر «{teacher.name}»\nیک مورد دیگر را برای تغییر انتخاب کنید:",
        reply_markup=keyboards.teacher_edit_fields(teacher.id),
    )


@router.message(F.text.in_({"مدیریت سپرها", "🛡 مدیریت سپرها"}))
async def shields(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not allowed(message):
        return
    await state.clear()
    items = await shield_service.list_shields(session)
    if not items:
        await message.answer("هنوز سپری ثبت نشده است.")
    for shield in items:
        await message.answer(
            f"🛡 {shield.name}\nشناسه: {shield.id}\n"
            f"کاهش آسیب: {shield.reduction_percent}% + {shield.flat_absorption} واحد\n"
            f"قیمت: {shield.purchase_price} سکه\nبازشدن در سطح: {shield.unlock_level}\n"
            f"وضعیت: {'فعال' if shield.is_active else 'غیرفعال'}\n"
            f"توضیح: {shield.description or '—'}",
            reply_markup=keyboards.shield_actions(shield.id),
        )
    await message.answer(
        "برای ساخت سپر جدید، /shield را بفرستید.", reply_markup=keyboards.main()
    )


@router.message(Command("shield"))
async def shield_start(message: Message, state: FSMContext) -> None:
    if allowed(message):
        await state.clear()
        await state.update_data(mode="create")
        await state.set_state(ShieldStates.name)
        await message.answer("نام سپر:")


async def shield_value(
    message: Message,
    state: FSMContext,
    key: str,
    next_state,
    prompt: str,
    *,
    minimum: int = 0,
) -> None:
    if not allowed(message) or not message.text:
        return
    try:
        value = number(message.text, key, minimum=minimum)
        if key == "reduction_percent" and value > 100:
            raise ValueError("درصد کاهش آسیب نمی‌تواند بیشتر از 100 باشد.")
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(**{key: value})
    await state.set_state(next_state)
    await message.answer(prompt)


@router.message(ShieldStates.name)
async def s_name(message, state):
    if not allowed(message) or not message.text:
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(ShieldStates.reduction_percent)
    await message.answer("درصد کاهش آسیب (0 تا 100):")


@router.message(ShieldStates.reduction_percent)
async def s_reduction(message, state):
    await shield_value(
        message,
        state,
        "reduction_percent",
        ShieldStates.flat_absorption,
        "جذب ثابت آسیب:",
    )


@router.message(ShieldStates.flat_absorption)
async def s_absorption(message, state):
    await shield_value(
        message,
        state,
        "flat_absorption",
        ShieldStates.purchase_price,
        "قیمت خرید به سکه:",
    )


@router.message(ShieldStates.purchase_price)
async def s_price(message, state):
    await shield_value(
        message, state, "purchase_price", ShieldStates.unlock_level, "سطح بازشدن:"
    )


@router.message(ShieldStates.unlock_level)
async def s_unlock(message, state):
    await shield_value(
        message,
        state,
        "unlock_level",
        ShieldStates.description,
        "توضیح سپر (برای خالی بودن - بفرستید):",
        minimum=1,
    )


@router.message(ShieldStates.description)
async def s_description(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    if not allowed(message) or not message.text:
        return
    data = await state.get_data()
    data["description"] = None if message.text.strip() == "-" else message.text.strip()
    mode = data.pop("mode", "create")
    shield_id = data.pop("shield_id", None)
    try:
        shield = (
            await shield_service.update_shield(session, shield_id, **data)
            if mode == "edit"
            else await shield_service.create_shield(session, **data)
        )
    except ValueError as exc:
        await state.clear()
        await message.answer(f"خطا در ذخیره سپر: {exc}", reply_markup=keyboards.main())
        return
    await state.clear()
    await message.answer(
        f"✅ سپر «{shield.name}» با شناسه {shield.id} ذخیره شد.",
        reply_markup=keyboards.main(),
    )


@router.callback_query(F.data.startswith("shield:"))
async def shield_callback(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    if not allowed(callback) or not callback.data:
        return
    parts = callback.data.split(":")
    if len(parts) < 3 or parts[0] != "shield":
        await callback.answer("دکمه منقضی یا نامعتبر است.", show_alert=True)
        return
    action = parts[1]
    raw_id = parts[2]
    try:
        shield_id = int(raw_id)
    except ValueError:
        await callback.answer("شناسه سپر نامعتبر است.", show_alert=True)
        return
    shield = await shield_service.get_shield(session, shield_id)
    if shield is None:
        await callback.answer("سپر پیدا نشد.", show_alert=True)
        return
    if action == "delete":
        deleted, shield = await shield_service.delete_shield(session, shield_id)
        await callback.answer(
            "حذف شد." if deleted else "این سپر استفاده شده؛ غیرفعال شد.",
            show_alert=True,
        )
        await safe_edit_reply_markup(callback.message, reply_markup=None)
        return
    if action == "edit":
        await state.clear()
        await callback.message.answer(
            f"ویرایش سپر «{shield.name}»\nیک مورد را برای تغییر انتخاب کنید:",
            reply_markup=keyboards.shield_edit_fields(shield_id),
        )
    elif action == "field" and len(parts) == 4:
        field = parts[3]
        if field not in SHIELD_EDIT_PROMPTS:
            await callback.answer("این گزینه معتبر نیست.", show_alert=True)
            return
        await state.clear()
        await state.update_data(edit_id=shield_id, edit_field=field)
        await state.set_state(ShieldStates.edit_value)
        await callback.message.answer(
            SHIELD_EDIT_PROMPTS[field], reply_markup=keyboards.cancel_keyboard()
        )
    elif action == "done":
        await state.clear()
        await callback.message.answer(
            f"ویرایش سپر «{shield.name}» تمام شد.", reply_markup=keyboards.main()
        )
    else:
        await callback.answer("عملیات ویرایش معتبر نیست.", show_alert=True)
        return
    await callback.answer()


@router.message(ShieldStates.edit_value)
async def shield_edit_value(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    if not allowed(message) or not message.text:
        return
    data = await state.get_data()
    field = data.get("edit_field")
    shield_id = data.get("edit_id")
    if field not in SHIELD_EDIT_PROMPTS or shield_id is None:
        await state.clear()
        await message.answer("فلو ویرایش منقضی شد.", reply_markup=keyboards.main())
        return
    value = message.text.strip()
    try:
        if field == "name":
            if not value:
                raise ValueError("نام سپر نمی‌تواند خالی باشد.")
        elif field == "description":
            value = None if value == "-" else value
        else:
            value = number(value, field, minimum=1 if field == "unlock_level" else 0)
            if field == "reduction_percent" and value > 100:
                raise ValueError("درصد کاهش آسیب نمی‌تواند بیشتر از 100 باشد.")
        shield = await shield_service.update_shield(
            session, int(shield_id), **{field: value}
        )
        if shield is None:
            raise ValueError("سپر پیدا نشد.")
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=keyboards.cancel_keyboard())
        return
    await state.clear()
    await message.answer("تغییر ذخیره شد.", reply_markup=keyboards.main())
    await message.answer(
        f"ویرایش سپر «{shield.name}»\nیک مورد دیگر را برای تغییر انتخاب کنید:",
        reply_markup=keyboards.shield_edit_fields(shield.id),
    )
