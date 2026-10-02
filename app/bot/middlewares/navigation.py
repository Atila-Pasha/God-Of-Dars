from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.bot.keyboards.main_menu import MENU_SECTION_LABELS

NAVIGATION_LABELS = MENU_SECTION_LABELS | {
    "منوی اصلی",
    "بازگشت به منو اصلی",
    "لغو",
    "❌ لغو",
}


class NavigationStateMiddleware(BaseMiddleware):
    """Route commands and menu buttons outside any pending text-input flow."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.text:
            text = event.text.strip()
            state = data.get("state")
            if state is not None and (
                text.startswith("/") or text in NAVIGATION_LABELS
            ):
                await state.clear()
                # FSM middleware loaded this before the message middlewares.
                # State filters must see the cleared state in this update too.
                data["raw_state"] = None
        return await handler(event, data)
