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

from app.bot.banners import MARKDOWN_V2, bold, emoji, escape, rich_plain, teacher_icon
from app.bot.callbacks import (
    LibraryCallback,
    LibraryShieldCallback,
    LibraryTeacherCallback,
    StudyCallback,
)
from app.bot.keyboards.buffet import SHIELD_ICONS
from app.bot.keyboards.library import (
    answer_keyboard,
    library_keyboard,
    shield_library_detail_keyboard,
    shield_library_keyboard,
    study_keyboard,
    teacher_library_detail_keyboard,
    teacher_library_keyboard,
)
from app.bot.keyboards.main_menu import MENU_SECTION_BY_LABEL, section_back_keyboard
from app.bot.teacher_lookup import matching_teachers
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
from app.services.shield_service import ShieldService
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
shield_service = ShieldService()
logger = logging.getLogger(__name__)

RESOURCE_LABELS = {
    "COIN": "طلا",
    "DIAMOND": "الماس",
    "BANANA": "موز",
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
    return f"مطالعه‌ات تکمیل شد و {amount} {label} دریافت کردی."


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


def _user_display_name(user: Any) -> str:
    name = " ".join(
        part
        for part in (
            getattr(user, "first_name", None),
            getattr(user, "last_name", None),
        )
        if part
    )
    return name or (
        f"@{user.username}" if getattr(user, "username", None) else str(user.id)
    )


def _group_reward_text(result: AnswerResult) -> str:
    rewards = tuple(
        reward for reward in getattr(result, "rewards", ()) if reward.amount > 0
    )
    if not rewards:
        return "بدون پاداش"
    return "، ".join(
        f"{RESOURCE_LABELS.get(_resource_name(reward), _resource_name(reward))}: "
        f"{reward.amount}"
        for reward in rewards
    )


async def _user_id(session: AsyncSession, message: Message | CallbackQuery) -> int:
    if message.from_user is None:
        raise UserInactiveError
    user = await user_service.get_active_by_telegram_user_id(
        session, message.from_user.id
    )
    return user.id


async def _show_library(target: Message | CallbackQuery) -> None:
    from app.bot.banners import MARKDOWN_V2, bold, emoji, section_entry_banner

    text = (
        f"{emoji('5825629907274703191', '📚')} {bold('کتابخانهٔ دانش')}\n\n"
        f"{emoji('5877214659227946561', '📖')} سؤال حل کن، مطالعه کن و قبل از نبرد دبیرها و سپرها رو بشناس\\."
    )
    if isinstance(target, CallbackQuery):
        if target.message is not None:
            target_message = cast(Message, target.message)
            await safe_edit_text(
                target_message,
                text,
                reply_markup=library_keyboard(),
                parse_mode=MARKDOWN_V2,
            )
    else:
        if isinstance(target, Message):
            await target.answer(
                section_entry_banner("کتابخانه"),
                reply_markup=section_back_keyboard(),
                parse_mode=MARKDOWN_V2,
            )
        await target.answer(
            text, reply_markup=library_keyboard(), parse_mode=MARKDOWN_V2
        )


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


async def _notify_callback(
    callback: CallbackQuery, text: str, *, parse_mode: str | None = None
) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.answer(text, parse_mode=parse_mode)
    except TelegramAPIError:
        logger.debug("Could not send library callback notice")


def _teacher_list_text(page: int, page_count: int) -> str:
    return (
        f"{emoji('5825697157872623308', '👨‍🏫')} {bold('تالار معرفی دبیرها')}\n\n"
        f"« صفحه {page + 1} از {page_count} »\n\n"
        f"برای دیدن پروندهٔ کامل، یک دبیر رو انتخاب کن {emoji('5888976517362355346', '👇')}"
    )


def _teacher_detail_content(teacher) -> str:
    details = (
        f"⚔️ آسیب پایه: {teacher.damage}\n"
        f"❤️ حداکثر جان: {teacher.max_hp}\n"
        f"🪙 قیمت خرید: {teacher.purchase_price} "
        f"{'الماس' if teacher.purchase_resource.value == 'DIAMOND' else 'طلا'}\n"
        f"💎 هزینه پایه (سطح 1 به 2): {teacher.upgrade_price} الماس\n"
        f"🎖 سطح بازشدن: {teacher.unlock_level}\n\n"
        f"✨ توانایی: {teacher.ability_text or 'تنظیم نشده'}\n"
        f"📝 توضیحات: {teacher.description or 'توضیحی ثبت نشده است.'}"
    )
    return (
        f"{teacher_icon(teacher.emoji)}    {bold(f'پروندهٔ دبیر | {teacher.name}')}\n\n"
        f"{rich_plain(details)}"
    )


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
            parse_mode=MARKDOWN_V2,
        )


def _shield_library_text() -> str:
    return (
        f"{emoji('5915888842568638290', '🛡️')} {bold('دانشنامهٔ سپرها')}\n\n"
        f"برای خواندن پروندهٔ هر سپر، دکمهٔ آن را انتخاب کن {emoji('5888976517362355346', '👇')}"
    )


def _shield_library_detail_text(shield) -> str:
    icon = emoji(SHIELD_ICONS.get(shield.name, "5825861861278490879"), "🛡️")
    currency = "الماس" if shield.purchase_resource.value == "DIAMOND" else "طلا"
    return (
        f"{icon} {bold(shield.name)}\n\n"
        f"{emoji('5825699618888884083', '🎖️')} سطح بازشدن: {escape(shield.unlock_level)}\n"
        f"{emoji('6039539366177541657', '⏳')} مدت محافظت: {escape(shield.duration_minutes)} دقیقه\n"
        f"{emoji('5825753314570018832' if currency == 'الماس' else '5825699971076202989', '💎' if currency == 'الماس' else '🪙')} "
        f"قیمت: {escape(shield.purchase_price)} {escape(currency)}\n\n"
        f"{bold('اثر سپر:')} {escape(shield.description or 'جلوگیری از حمله به دژ')}"
    )


async def _show_shield_list(callback: CallbackQuery, session: AsyncSession) -> None:
    shields = await shield_service.catalog(session, player_level=None)
    if callback.message is not None:
        await safe_edit_text(
            cast(Message, callback.message),
            _shield_library_text(),
            reply_markup=shield_library_keyboard(shields),
            parse_mode=MARKDOWN_V2,
        )


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    F.text.regexp(r"^معرفی(?:\s+.+)?$"),
)
async def group_teacher_introduction(message: Message, session: AsyncSession) -> None:
    name = (message.text or "")[len("معرفی") :].strip()
    if not name:
        await message.answer("فرمت صحیح: معرفی نام دبیر")
        return
    teachers = await teacher_service.public_teachers(session)
    matches = matching_teachers(teachers, name)
    if not matches:
        await message.answer("دبیری با این نام پیدا نشد.")
        return
    if len(matches) > 1:
        await message.answer(
            "چند دبیر با این نام پیدا شد؛ اسم کامل دبیر را بنویسید: "
            + "، ".join(teacher.name for teacher in matches)
        )
        return
    await message.answer(_teacher_detail_content(matches[0]), parse_mode=MARKDOWN_V2)


@router.message(F.text == LIBRARY_LABEL)
async def library_handler(
    message: Message, state: FSMContext, session: AsyncSession | None = None
) -> None:
    await state.clear()
    await _show_library(message)
    if session is not None and message.from_user is not None:
        try:
            user_id = await _user_id(session, message)
            _, reward = await study_service.settle(session, user_id)
        except (UserInactiveError, SchoolUserNotFound):
            return
        if reward is not None:
            await message.answer(_study_reward_text(reward))


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
            user_id = await _user_id(session, callback)
            prior = await question_service.repository.get_daily_answer(
                session, question_id=daily_question.id, user_id=user_id
            )
            if prior is not None:
                await _notify_callback(
                    callback,
                    f"{emoji('5834600998739381814', '🛑')} این سؤال را قبلاً پاسخ داده‌اید\\.",
                    parse_mode=MARKDOWN_V2,
                )
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
        elif callback_data.action == "answer":
            if await state.get_state() == LibraryState.waiting_daily_answer.state:
                await _notify_callback(callback, "جواب رو ارسال کن.")
            else:
                await _notify_callback(callback, "ابتدا سؤال روزانه را باز کن.")
        elif callback_data.action == "group":
            await _notify_callback(
                callback,
                "برای پاسخ به سؤال گروهی، روی خود پیام سؤال Reply بزن.",
            )
        elif callback_data.action == "study":
            user_id = await _user_id(session, callback)
            active, reward = await study_service.settle(session, user_id)
            if active is not None and reward is None:
                await _notify_callback(
                    callback,
                    f"{emoji('5823388325188214894', '✅')} {bold('ساعت مطالعه فعال است.')}\n\n"
                    f"> زمان باقی‌مانده: {escape(_study_time(active.ends_at))}",
                    parse_mode=MARKDOWN_V2,
                )
                return
            if reward is not None:
                await _show_library(callback)
                await _notify_callback(callback, _study_reward_text(reward))
                return
            if callback.message is not None:
                await safe_edit_text(
                    cast(Message, callback.message),
                    "📖 ثبت مطالعه\n\nیک پک مطالعه انتخاب کنید. تا پایان پک امکان انتخاب پک دیگر وجود ندارد:",
                    reply_markup=study_keyboard(await study_service.packs(session)),
                )
        elif callback_data.action == "teachers":
            await _show_teacher_list(callback, session, 0)
        elif callback_data.action == "shields":
            await _show_shield_list(callback, session)
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
    except (UserInactiveError, SchoolUserNotFound, LibraryError):
        await state.clear()
        await _notify_callback(
            callback, "امکان استفاده از کتابخانه در حال حاضر وجود ندارد."
        )


@router.callback_query(LibraryShieldCallback.filter())
async def library_shield_callback(
    callback: CallbackQuery,
    callback_data: LibraryShieldCallback,
    session: AsyncSession,
) -> None:
    await _safe_callback_answer(callback)
    if callback_data.action == "back":
        await _show_shield_list(callback, session)
        return
    shield = await shield_service.get_shield(session, callback_data.shield_id)
    if shield is None or not shield.is_active:
        await _notify_callback(callback, "این سپر در دسترس نیست.")
        return
    if callback.message is not None:
        await safe_edit_text(
            cast(Message, callback.message),
            _shield_library_detail_text(shield),
            reply_markup=shield_library_detail_keyboard(),
            parse_mode=MARKDOWN_V2,
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
        await safe_edit_text(
            cast(Message, callback.message),
            _teacher_detail_content(teacher),
            reply_markup=teacher_library_detail_keyboard(callback_data.page),
            parse_mode=MARKDOWN_V2,
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
            await _notify_callback(
                callback,
                f"⏳ یک پک فعال دارید. زمان باقی‌مانده: {_study_time(exc.study.ends_at)}",
            )
            return
        except (StudyPackNotFound, StudyError):
            await _notify_callback(callback, "این پک مطالعه در دسترس نیست.")
            return
        pack = await study_service.get_pack(session, callback_data.pack_key)
        if pack is None:
            await _notify_callback(callback, "این پک مطالعه دیگر فعال نیست.")
            return
        label = "طلا" if pack.reward_resource == "COIN" else "الماس"
        text = (
            f"✅ مطالعه شروع شد.\n\n⏳ مدت مطالعه: {pack.duration_minutes} دقیقه\n"
            f"🎁 پاداش پایان: {pack.reward_amount} {label}\n\n"
            "تا پایان این زمان امکان انتخاب پک دیگر ندارید."
        )
        if result.completed_reward:
            await _notify_callback(
                callback, _study_reward_text(result.completed_reward)
            )
        if callback.message is not None:
            await safe_edit_text(
                cast(Message, callback.message), text, reply_markup=library_keyboard()
            )
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
    if (
        message.from_user is None
        or message.text is None
        or message.reply_to_message is None
    ):
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
        if result.correct:
            response = (
                f"✅ درست جواب دادی! {_user_display_name(message.from_user)} "
                f"زودتر از همه پاسخ داد و {_group_reward_text(result)} دریافت کرد."
            )
            await _answer_group_reply(message, response)
    # The service still persists wrong attempts and rejects invalid ones, but
    # the group receives a message only for the winning correct answer.
    except (WrongGroup, DuplicateAnswer, QuestionExpired, QuestionAlreadyAnswered):
        return
    except (QuestionNotFound, UserInactiveError, LibraryError):
        logger.exception("Could not process group-question reply")


async def _answer_group_reply(message: Message, text: str) -> None:
    await message.answer(
        text,
        reply_to_message_id=message.message_id,
    )
