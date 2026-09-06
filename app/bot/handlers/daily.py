from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.daily import daily_keyboard
from app.bot.keyboards.main_menu import MENU_SECTION_BY_LABEL
from app.bot.middlewares.subscription import subscription_service
from app.models.daily_quest import DailyQuestProgress
from app.services.daily_quest_service import DailyQuestService
from app.services.user_service import UserService

router = Router(name="daily")
service = DailyQuestService()
user_service = UserService()
DAILY_LABEL = next(
    label for label, section in MENU_SECTION_BY_LABEL.items() if section == "daily"
)


async def _show(target, session: AsyncSession, user_id: int):
    quests = await service.list(session, datetime.now(UTC).date(), active_only=True)
    if not quests:
        text = "🎯 فعالیت‌های روزانه\n\nامروز فعالیتی تعریف نشده است."
        markup = None
    else:
        progresses = []
        for quest in quests:
            progress = await service.repository.progress(session, user_id, quest.id)
            if progress is None:
                progress = DailyQuestProgress(
                    user_id=user_id,
                    quest_id=quest.id,
                    activity_date=quest.activity_date,
                )
                session.add(progress)
                await session.flush()
            progress.quest = quest
            progresses.append(progress)
        text = "🎯 فعالیت‌های روزانه\n\nفعالیت‌های امروز را کامل کن و جایزه بگیر:"
        markup = daily_keyboard(progresses)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(F.text == DAILY_LABEL)
async def daily_message(message: Message, session: AsyncSession):
    if message.from_user:
        user = await user_service.get_active_by_telegram_user_id(
            session, message.from_user.id
        )
        await _show(message, session, user.id)


@router.callback_query(F.data.startswith("daily:"))
async def daily_callback(callback: CallbackQuery, session: AsyncSession):
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await user_service.get_active_by_telegram_user_id(
        session, callback.from_user.id
    )
    parts = callback.data.split(":", 2)
    action = parts[1]
    value = parts[2] if len(parts) > 2 else ""
    if action == "join":
        progress = await service.repository.progress(
            session, user.id, int(value), for_update=True
        )
        if progress is None:
            await callback.answer("فعالیت پیدا نشد.", show_alert=True)
            return
        quest = await service.repository.get(session, progress.quest_id)
        channel = (quest.quest_metadata or {}).get("channel")
        if not channel or not await subscription_service.is_member_in_channel(
            callback.bot, user.telegram_user_id, channel
        ):
            await callback.answer("ابتدا عضو کانال شوید.", show_alert=True)
            return
        await service.record_event(
            session,
            user_id=user.id,
            event_type="JOIN_CHANNEL",
            event_id=f"{quest.id}:{channel}",
            event_metadata={"channel": channel},
        )
        await callback.answer("عضویت تأیید شد.")
        await _show(callback, session, user.id)
        return
    if action == "claim":
        async def membership_checker(channel):
            return await subscription_service.is_member_in_channel(
                callback.bot, user.telegram_user_id, channel
            )
        result = await service.claim(
            session,
            user_id=user.id,
            progress_id=int(value),
            membership_checker=membership_checker,
        )
        await callback.answer(
            "جایزه دریافت شد."
            if result
            else "این فعالیت هنوز کامل نشده یا قبلاً دریافت شده است.",
            show_alert=not bool(result),
        )
        await _show(callback, session, user.id)
    else:
        await callback.answer()
