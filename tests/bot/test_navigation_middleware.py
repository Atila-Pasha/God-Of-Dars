from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Chat, Message, Update, User

from app.bot.handlers.library import LibraryState
from app.bot.middlewares.navigation import NavigationStateMiddleware
from app.bot.states import AttackMenuStates, BuffetStates, ChanceCardStates


@pytest.mark.parametrize(
    "pending_state",
    [
        LibraryState.waiting_daily_answer,
        ChanceCardStates.waiting_captcha,
        BuffetStates.convert_amount,
        AttackMenuStates.waiting_target,
    ],
)
@pytest.mark.parametrize(
    "text", ["/start", "/help", "معدن منابع", "بازگشت به منو اصلی", "4"]
)
async def test_navigation_cannot_be_consumed_as_pending_input(pending_state, text):
    dispatcher = Dispatcher()
    dispatcher.message.outer_middleware(NavigationStateMiddleware())
    input_router = Router()
    navigation_router = Router()
    routed = []

    @input_router.message(pending_state, F.text)
    async def handle_input(message: Message):
        routed.append("input")

    @navigation_router.message(F.text)
    async def handle_navigation(message: Message):
        routed.append("navigation")

    dispatcher.include_routers(input_router, navigation_router)
    bot = Bot("123456:test-only")
    try:
        state = dispatcher.fsm.get_context(bot=bot, chat_id=42, user_id=42)
        await state.set_state(pending_state)
        await state.update_data(question_id=7)
        message = Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(id=42, type="private"),
            from_user=User(id=42, is_bot=False, first_name="test"),
            text=text,
        )
        await dispatcher.feed_update(bot, Update(update_id=1, message=message))
        if text == "4":
            assert routed == ["input"]
            assert await state.get_state() == pending_state.state
            assert await state.get_data() == {"question_id": 7}
        else:
            assert routed == ["navigation"]
            assert await state.get_state() is None
            assert await state.get_data() == {}
    finally:
        await dispatcher.storage.close()
        await bot.session.close()


async def test_non_text_message_does_not_clear_input_state():
    state = AsyncMock()
    handler = AsyncMock()
    data = {"state": state, "raw_state": LibraryState.waiting_daily_answer.state}
    message = Message(
        message_id=1, date=datetime.now(UTC), chat=Chat(id=42, type="private")
    )
    await NavigationStateMiddleware()(handler, message, data)
    state.clear.assert_not_awaited()
    handler.assert_awaited_once_with(message, data)
