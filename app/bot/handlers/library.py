from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, cast

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import LibraryCallback, LibraryTeacherCallback, StudyCallback
from app.bot.custom_emojis import custom_emoji_entity
from app.bot.keyboards.library import (
    answer_keyboard,
    library_keyboard,
    study_keyboard,
    teacher_library_detail_keyboard,
    teacher_library_keyboard,
)
from app.bot.keyboards.main_menu import MENU_SECTION_BY_LABEL
from app.bot.utils.telegram import safe_edit_text
from app.services.library_errors import (
    DuplicateAnswer,
    LibraryError,
    QuestionAlreadyAnswered,
    QuestionExpired,
    QuestionNotFound,
    WrongGroup,
)
from app.services.question_service import AnswerResult, QuestionService
from app.services.school_errors import SchoolUserNotFound, TeacherNotFound
from app.services.study_service import (
    StudyAlreadyActive,
    StudyError,
    StudyPackNotFound,
    StudyService,
)
from app.services.teacher_service import TeacherService
from app.services.user_service import UserInactiveError, UserService

router = Router(name="library")
question_service = QuestionService()
user_service = UserService()
study_service = StudyService()
teacher_service = TeacherService()
logger = logging.getLogger(__name__)

RESOURCE_LABELS = {
    "COIN": "طلا",
    "DIAMOND": "الماس",
    "BANANA": "XP",
}

LIBRARY_LABEL = next(
    label for label, section in MENU_SECTION_BY_LABEL.items() if section == "library"
)
TEACHERS_PER_PAGE = 5


class LibraryState(StatesGroup):
    waiting_daily_answer = State()


def _now() -> datetime:
    return datetime.now(UTC)


def _question_text(
    question: Any, *, title: str, expires_at: datetime | None = None
) -> str:
    expires = question.expires_at if expires_at is None else expires_at
    expiration_text = "بدون زمان انقضا"
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        expiration_text = expires.astimezone().strftime("%Y-%m-%d %H:%M")
    return f"{title}\n\n❓ {question.question_text}\n\n⏳ مهلت: {expiration_text}"


def _study_time(ends_at: datetime) -> str:
    end = ends_at if ends_at.tzinfo else ends_at.replace(tzinfo=UTC)
    seconds = max(0, int((end - _now()).total_seconds()))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def _study_reward_text(reward: tuple | None) -> str:
    if reward is None:
        return ""
    resource, amount = reward
    label = "طلا" if resource.value == "COIN" else "الماس"
    return f"\n\n🎁 پاداش مطالعه آماده شد: {amount} {label}"


def _result_text(result: AnswerResult) -> str:
    if result.correct:
        rewards = getattr(result, "rewards", None)
        if rewards is None:
            reward = getattr(result, "reward", None)
            rewards = (reward,) if reward is not None else ()
        rewards = tuple(reward for reward in rewards if reward and reward.amount > 0)
        if not rewards:
            return "✅ درست جواب دادی!\n\nپاسخ تو ثبت شد؛ این سؤال پاداشی نداشت."
        reward_text = "\n".join(
            f"{RESOURCE_LABELS.get(_resource_name(reward), _resource_name(reward))}: "
            f"{reward.amount}"
            for reward in rewards
        )
        return f"✅ درست جواب دادی!\n\nمقدار منابع دریافتی:\n{reward_text}"
    return "❌ پاسخ شما اشتباه بود.\n\nپاسخ شما ثبت شد؛ امکان تلاش دوباره وجود ندارد."


def _resource_name(reward: Any) -> str:
    resource_type = reward.resource_type
    return getattr(resource_type, "value", str(resource_type))


async def _user_id(session: AsyncSession, message: Message | CallbackQuery) -> int:
    if message.from_user is None:
        raise UserInactiveError
    user = await user_service.get_active_by_telegram_user_id(
        session, message.from_user.id
    )
    return user.id


async def _show_library(target: Message | CallbackQuery) -> None:
    text = "📚 کتابخانه\n\nیکی از بخش‌های کتابخانه را انتخاب کنید:"
    if isinstance(target, CallbackQuery):
        if target.message is not None:
            target_message = cast(Message, target.message)
            await safe_edit_text(target_message, text, reply_markup=library_keyboard())
    else:
        await target.answer(text, reply_markup=library_keyboard())


async def _safe_callback_answer(
    callback: CallbackQuery, text: str | None = None, *, show_alert: bool = False
) -> None:
    """Acknowledge a callback without allowing an expired query to crash polling."""
    try:
        if text is None:
            await callback.answer()
        else:
            await callback.answer(text, show_alert=show_alert)
    except TelegramAPIError:
        logger.debug("Ignoring an expired or already-answered library callback")


async def _notify_callback(callback: CallbackQuery, text: str) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.answer(text)
    except TelegramAPIError:
        logger.debug("Could not send library callback notice")


def _teacher_list_text(page: int, page_count: int) -> str:
    return f"👨‍🏫 معرفی دبیرها\n\nصفحه {page + 1} از {page_count}\nیک دبیر را انتخاب کنید:"


def _teacher_detail_content(teacher) -> tuple[str, list]:
    icon, entity = custom_emoji_entity(teacher.emoji, fallback="👨‍🏫")
    text = (
        f"{icon} {teacher.name}\n\n"
        f"⚔️ آسیب پایه: {teacher.damage}\n"
        f"❤️ حداکثر جان: {teacher.max_hp}\n"
        f"🪙 قیمت خرید: {teacher.purchase_price} سکه\n"
        f"💎 قیمت ارتقا: {teacher.upgrade_price} الماس\n"
        f"🎖 سطح بازشدن: {teacher.unlock_level}\n\n"
        f"✨ توانایی: {teacher.ability_text or 'تنظیم نشده'}\n"
        f"📝 توضیحات: {teacher.description or 'توضیحی ثبت نشده است.'}"
    )
    return text, [entity] if entity is not None else []


async def _show_teacher_list(
    target: CallbackQuery, session: AsyncSession, page: int
) -> None:
    teachers = await teacher_service.public_teachers(session)
    page_count = max(1, (len(teachers) + TEACHERS_PER_PAGE - 1) // TEACHERS_PER_PAGE)
    page = max(0, min(page, page_count - 1))
    start = page * TEACHERS_PER_PAGE
    items = teachers[start : start + TEACHERS_PER_PAGE]
    if target.message is not None:
        await safe_edit_text(
            cast(Message, target.message),
            _teacher_list_text(page, page_count),
            reply_markup=teacher_library_keyboard(
                items, page=page, page_count=page_count
            ),
        )


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.regexp(r"^معرفی(?:\s+.+)?$"),
)
async def group_teacher_introduction(
    message: Message, session: AsyncSession
) -> None:
    name = (message.text or "")[len("معرفی") :].strip()
    if not name:
        await message.answer("فرمت صحیح: معرفی نام دبیر")
        return
    teachers = await teacher_service.public_teachers(session)
    teacher = next(
        (item for item in teachers if item.name.casefold() == name.casefold()),
        None,
    )
    if teacher is None:
        await message.answer("دبیری با این نام پیدا نشد.")
        return
    text, entities = _teacher_detail_content(teacher)
    await message.answer(text, entities=entities)


@router.message(F.text == LIBRARY_LABEL)
async def library_handler(message: Message, state: FSMContext, session: AsyncSession | None = None) -> None:
    await state.clear()
    await _show_library(message)
    if session is not None and message.from_user is not None:
        try:
            user_id = await _user_id(session, message)
            _, reward = await study_service.settle(session, user_id)
        except (UserInactiveError, SchoolUserNotFound):
            return
        if reward is not None:
            await message.answer(_study_reward_text(reward).strip(), reply_markup=library_keyboard())


@router.callback_query(LibraryCallback.filter())
async def library_callback_handler(
    callback: CallbackQuery,
    callback_data: LibraryCallback,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    # Telegram expects callback_query.answer within a short deadline. Do this
    # before the database lookup, then use a normal message for notices.
    await _safe_callback_answer(callback)
    if callback.from_user is None:
        return

    try:
        if callback_data.action == "daily":
            daily_question = await question_service.get_active_daily_question(
                session, now=_now()
            )
            if daily_question is None:
                await _notify_callback(callback, "فعلاً سؤال روزانه‌ای وجود ندارد.")
                return
            await state.set_state(LibraryState.waiting_daily_answer)
            await state.update_data(question_id=daily_question.id)
            if callback.message is not None:
                callback_message = cast(Message, callback.message)
                await safe_edit_text(
                    callback_message,
                    _question_text(daily_question, title="📅 سؤال روزانه"),
                    reply_markup=answer_keyboard(),
                )
        elif callback_data.action == "group":
            await _notify_callback(
                callback,
                "برای پاسخ به سؤال گروهی، روی خود پیام سؤال Reply بزن.",
            )
        elif callback_data.action == "study":
            user_id = await _user_id(session, callback)
            active, reward = await study_service.settle(session, user_id)
            if active is not None and reward is None:
                await _notify_callback(callback, f"📖 مطالعه فعال است. زمان باقی‌مانده: {_study_time(active.ends_at)}")
                return
            if callback.message is not None:
                await safe_edit_text(
                    cast(Message, callback.message),
                    "📖 ثبت مطالعه\n\nیک پک مطالعه انتخاب کنید. تا پایان پک امکان انتخاب پک دیگر وجود ندارد:",
                    reply_markup=study_keyboard(study_service.packs()),
                )
            if reward is not None:
                await _notify_callback(callback, _study_reward_text(reward).strip())
        elif callback_data.action == "teachers":
            await _show_teacher_list(callback, session, 0)
        elif callback_data.action == "cancel":
            await state.clear()
            if callback.message is not None:
                if callback.message.chat.type in {"group", "supergroup"}:
                    await safe_edit_text(callback.message, "❌ پاسخ‌گویی لغو شد.")
                else:
                    await _show_library(callback)
        else:
            await state.clear()
            if callback.message is not None:
                await _show_library(callback)
    except (UserInactiveError, LibraryError):
        await state.clear()
        await _notify_callback(
            callback, "امکان استفاده از کتابخانه در حال حاضر وجود ندارد."
        )


@router.callback_query(LibraryTeacherCallback.filter())
async def library_teacher_callback(
    callback: CallbackQuery,
    callback_data: LibraryTeacherCallback,
    session: AsyncSession,
) -> None:
    await _safe_callback_answer(callback)
    if callback_data.action in {"page", "back"}:
        if callback_data.action == "back":
            if callback.message is not None:
                await _show_library(callback)
        else:
            await _show_teacher_list(callback, session, callback_data.page)
        return
    try:
        teacher = await teacher_service.catalog_teacher(
            session, callback_data.teacher_id
        )
    except TeacherNotFound:
        await _notify_callback(callback, "این دبیر در دسترس نیست.")
        return
    if teacher is None or not teacher.is_active:
        await _notify_callback(callback, "این دبیر در دسترس نیست.")
        return
    if callback.message is not None:
        text, entities = _teacher_detail_content(teacher)
        await safe_edit_text(
            cast(Message, callback.message),
            text,
            reply_markup=teacher_library_detail_keyboard(callback_data.page),
            entities=entities,
        )


@router.callback_query(StudyCallback.filter())
async def study_callback_handler(
    callback: CallbackQuery,
    callback_data: StudyCallback,
    session: AsyncSession,
) -> None:
    await _safe_callback_answer(callback)
    if callback.from_user is None:
        return
    try:
        user_id = await _user_id(session, callback)
        try:
            result = await study_service.start(session, user_id, callback_data.pack_key)
        except StudyAlreadyActive as exc:
            await _notify_callback(callback, f"⏳ یک پک فعال دارید. زمان باقی‌مانده: {_study_time(exc.study.ends_at)}")
            return
        except (StudyPackNotFound, StudyError):
            await _notify_callback(callback, "این پک مطالعه در دسترس نیست.")
            return
        pack = study_service.packs()[callback_data.pack_key]
        label = "طلا" if pack.reward_resource.value == "COIN" else "الماس"
        text = (
            f"✅ مطالعه شروع شد.\n\n⏳ مدت مطالعه: {pack.duration_minutes} دقیقه\n"
            f"🎁 پاداش پایان: {pack.reward_amount} {label}\n\n"
            "تا پایان این زمان امکان انتخاب پک دیگر ندارید."
        )
        if result.completed_reward:
            text = _study_reward_text(result.completed_reward).strip() + "\n\n" + text
        if callback.message is not None:
            await safe_edit_text(cast(Message, callback.message), text, reply_markup=library_keyboard())
    except (UserInactiveError, SchoolUserNotFound, StudyError):
        await _notify_callback(callback, "امکان ثبت مطالعه در حال حاضر وجود ندارد.")


@router.message(LibraryState.waiting_daily_answer, F.text)
async def daily_answer_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    question_id = data.get("question_id")
    if question_id is None or message.from_user is None or message.text is None:
        await state.clear()
        return
    try:
        user_id = await _user_id(session, message)
        result = await question_service.answer_daily_question(
            session, user_id, question_id, message.text, now=_now()
        )
        await message.answer(
            _result_text(result),
            reply_markup=library_keyboard(),
            reply_to_message_id=getattr(message, "message_id", None),
        )
    except DuplicateAnswer:
        await message.answer(
            "این سؤال را قبلاً پاسخ داده‌اید.", reply_markup=library_keyboard()
        )
    except QuestionExpired:
        await message.answer(
            "مهلت پاسخ‌گویی به این سؤال تمام شده است.", reply_markup=library_keyboard()
        )
    except QuestionAlreadyAnswered:
        await message.answer(
            "این سؤال قبلاً پاسخ داده شده است.", reply_markup=library_keyboard()
        )
    except (QuestionNotFound, UserInactiveError, LibraryError):
        await message.answer("پاسخ شما ثبت نشد. لطفاً دوباره از کتابخانه وارد شوید.")
    finally:
        await state.clear()


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.reply_to_message,
    F.text,
    ~F.text.startswith("/"),
)
async def group_reply_answer_handler(
    message: Message,
    session: AsyncSession,
) -> None:
    if message.from_user is None or message.text is None:
        return

    publication = await question_service.get_group_question_by_message(
        session,
        telegram_chat_id=message.chat.id,
        telegram_message_id=message.reply_to_message.message_id,
    )
    if publication is None:
        return

    try:
        user = await user_service.get_or_create_from_telegram(
            session, message.from_user
        )
        result = await question_service.answer_group_question(
            session,
            user.id,
            publication.question_id,
            publication.group_id,
            message.text,
            now=_now(),
        )
        await _answer_group_reply(message, _result_text(result))
    except WrongGroup:
        await _answer_group_reply(message, "این سؤال به گروه فعلی مربوط نیست.")
    except DuplicateAnswer:
        await _answer_group_reply(message, "پاسخ شما قبلاً برای این سؤال ثبت شده است.")
    except QuestionExpired:
        await _answer_group_reply(message, "مهلت پاسخ‌گویی به سؤال گروه تمام شده است.")
    except QuestionAlreadyAnswered:
        winner = await question_service.first_group_answer(session, publication.id)
        winner_name = _answerer_name(winner)
        await _answer_group_reply(
            message,
            f"⏰ دیر اومدی رفیق! {winner_name} زودتر پاسخ داده و جوابش ثبت شده.",
        )
    except (QuestionNotFound, UserInactiveError, LibraryError):
        await _answer_group_reply(message, "پاسخ شما ثبت نشد؛ دوباره امتحان کن.")


async def _answer_group_reply(message: Message, text: str) -> None:
    await message.answer(
        text,
        reply_to_message_id=message.message_id,
    )


def _answerer_name(answer: Any) -> str:
    if answer is None or answer.user is None:
        return "یک نفر"
    return (
        " ".join(
            part for part in (answer.user.first_name, answer.user.last_name) if part
        )
        or "یک نفر"
    )
