from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import LibraryCallback
from app.bot.keyboards.library import (
    answer_keyboard,
    group_answer_keyboard,
    library_keyboard,
)
from app.bot.keyboards.main_menu import MENU_SECTION_BY_LABEL
from app.services.library_errors import (
    DuplicateAnswer,
    LibraryError,
    QuestionAlreadyAnswered,
    QuestionExpired,
    QuestionNotFound,
    WrongGroup,
)
from app.services.question_service import AnswerResult, QuestionService
from app.services.user_service import UserInactiveError, UserService

router = Router(name="library")
question_service = QuestionService()
user_service = UserService()

LIBRARY_LABEL = next(
    label for label, section in MENU_SECTION_BY_LABEL.items() if section == "library"
)


class LibraryState(StatesGroup):
    waiting_daily_answer = State()
    waiting_group_answer = State()


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


def _result_text(result: AnswerResult) -> str:
    if result.correct:
        if result.reward is None:
            return "✅ پاسخ شما درست بود!\n\nپاسخ شما با موفقیت ثبت شد."
        return (
            "✅ پاسخ شما درست بود!\n\n"
            f"🎁 پاداش: {result.reward.amount} {result.reward.resource_type.value}"
        )
    return "❌ پاسخ شما اشتباه بود.\n\nپاسخ شما ثبت شد؛ امکان تلاش دوباره وجود ندارد."


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
            await target_message.edit_text(text, reply_markup=library_keyboard())
    else:
        await target.answer(text, reply_markup=library_keyboard())


@router.message(Command("library"))
@router.message(F.text == LIBRARY_LABEL)
async def library_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_library(message)


@router.callback_query(LibraryCallback.filter())
async def library_callback_handler(
    callback: CallbackQuery,
    callback_data: LibraryCallback,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return

    try:
        if callback_data.action == "daily":
            daily_question = await question_service.get_active_daily_question(
                session, now=_now()
            )
            if daily_question is None:
                await callback.answer("فعلاً سؤال روزانه‌ای وجود ندارد.", show_alert=True)
                return
            await state.set_state(LibraryState.waiting_daily_answer)
            await state.update_data(question_id=daily_question.id)
            if callback.message is not None:
                callback_message = cast(Message, callback.message)
                await callback_message.edit_text(
                    _question_text(daily_question, title="📅 سؤال روزانه"),
                    reply_markup=answer_keyboard(),
                )
        elif callback_data.action == "group":
            if callback.message is None or not hasattr(callback.message, "chat"):
                await callback.answer("این گزینه فقط داخل گروه قابل استفاده است.", show_alert=True)
                return
            callback_message = cast(Message, callback.message)
            group_question = await question_service.get_active_group_question_for_chat(
                session,
                telegram_chat_id=callback_message.chat.id,
                now=_now(),
            )
            if group_question is None:
                await callback.answer("فعلاً سؤال فعالی برای این گروه وجود ندارد.", show_alert=True)
                return
            await state.set_state(LibraryState.waiting_group_answer)
            await state.update_data(
                question_id=group_question.question_id,
                group_id=group_question.group_id,
            )
            await callback_message.edit_text(
                _question_text(
                    group_question.question,
                    title="👥 سؤال گروه",
                    expires_at=group_question.expires_at
                    or group_question.question.expires_at,
                ),
                reply_markup=group_answer_keyboard(),
            )
        else:
            await state.clear()
            if callback.message is not None:
                await _show_library(callback)
        await callback.answer()
    except (UserInactiveError, LibraryError):
        await state.clear()
        await callback.answer("امکان استفاده از کتابخانه در حال حاضر وجود ندارد.", show_alert=True)


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
        await message.answer(_result_text(result), reply_markup=library_keyboard())
    except DuplicateAnswer:
        await message.answer("این سؤال را قبلاً پاسخ داده‌اید.", reply_markup=library_keyboard())
    except QuestionExpired:
        await message.answer("مهلت پاسخ‌گویی به این سؤال تمام شده است.", reply_markup=library_keyboard())
    except QuestionAlreadyAnswered:
        await message.answer("این سؤال قبلاً پاسخ داده شده است.", reply_markup=library_keyboard())
    except (QuestionNotFound, UserInactiveError, LibraryError):
        await message.answer("پاسخ شما ثبت نشد. لطفاً دوباره از کتابخانه وارد شوید.")
    finally:
        await state.clear()


@router.message(LibraryState.waiting_group_answer, F.text)
async def group_answer_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    question_id = data.get("question_id")
    group_id = data.get("group_id")
    if (
        question_id is None
        or group_id is None
        or message.from_user is None
        or message.text is None
    ):
        await state.clear()
        return
    try:
        user_id = await _user_id(session, message)
        result = await question_service.answer_group_question(
            session,
            user_id,
            question_id,
            group_id,
            message.text,
            now=_now(),
        )
        await message.answer(_result_text(result), reply_markup=library_keyboard())
    except WrongGroup:
        await message.answer("این سؤال به گروه فعلی مربوط نیست.", reply_markup=library_keyboard())
    except DuplicateAnswer:
        await message.answer("شما قبلاً به این سؤال پاسخ داده‌اید.", reply_markup=library_keyboard())
    except QuestionExpired:
        await message.answer("مهلت پاسخ‌گویی به سؤال گروه تمام شده است.", reply_markup=library_keyboard())
    except QuestionAlreadyAnswered:
        await message.answer("برندهٔ این سؤال قبلاً مشخص شده است.", reply_markup=library_keyboard())
    except (QuestionNotFound, UserInactiveError, LibraryError):
        await message.answer("پاسخ شما ثبت نشد. لطفاً دوباره از کتابخانه وارد شوید.")
    finally:
        await state.clear()
