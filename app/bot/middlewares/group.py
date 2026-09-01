from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, TelegramObject
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.main_menu import MENU_SECTION_LABELS
from app.services.group_service import GroupService

logger = logging.getLogger(__name__)

GROUP_CHAT_TYPES = frozenset({"group", "supergroup"})
ALLOWED_GROUP_COMMANDS = frozenset({"stat", "attack"})
ALLOWED_GROUP_CALLBACKS = frozenset({"library:group", "library:cancel"})


class GroupAccessMiddleware(BaseMiddleware):
    """Register groups and keep private-only bot features out of group chats."""

    def __init__(self, group_service: GroupService | None = None) -> None:
        self.group_service = group_service or GroupService()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and self._is_group_message(event):
            await self._register_group(event, data.get("session"))
            if not self._message_is_allowed(event):
                if self._is_menu_input(event):
                    await self._remove_menu_keyboard(event)
                return None
        elif isinstance(event, CallbackQuery) and self._is_group_callback(event):
            if not self._callback_is_allowed(event):
                return None
        return await handler(event, data)

    async def _register_group(
        self, message: Message, session: AsyncSession | None
    ) -> None:
        if session is None or message.chat is None:
            return
        title = message.chat.title or message.chat.username or "گروه بدون نام"
        try:
            await self.group_service.register_chat(
                session,
                telegram_chat_id=message.chat.id,
                title=title,
                username=message.chat.username,
            )
        except SQLAlchemyError:
            logger.exception("Could not register Telegram group %s", message.chat.id)

    @staticmethod
    def _is_group_message(message: Message) -> bool:
        return message.chat.type in GROUP_CHAT_TYPES

    @staticmethod
    def _is_group_callback(callback: CallbackQuery) -> bool:
        return bool(
            callback.message is not None
            and callback.message.chat.type in GROUP_CHAT_TYPES
        )

    @staticmethod
    def _message_is_allowed(message: Message) -> bool:
        text = (message.text or "").strip()
        if not text:
            return True
        if text.startswith("/"):
            command = text.split(maxsplit=1)[0].split("@", maxsplit=1)[0]
            return command.removeprefix("/").casefold() in ALLOWED_GROUP_COMMANDS
        return text not in MENU_SECTION_LABELS

    @staticmethod
    def _is_menu_input(message: Message) -> bool:
        text = (message.text or "").strip()
        if text in MENU_SECTION_LABELS:
            return True
        if text.startswith("/"):
            command = text.split(maxsplit=1)[0].split("@", maxsplit=1)[0]
            return command.removeprefix("/").casefold() == "start"
        return False

    @staticmethod
    async def _remove_menu_keyboard(message: Message) -> None:
        try:
            await message.answer(
                "منوی ربات در گروه غیرفعال است.",
                reply_markup=ReplyKeyboardRemove(),
            )
        except Exception:  
            logger.debug(
                "Could not remove the bot menu keyboard in group %s",
                message.chat.id,
                exc_info=True,
            )

    @staticmethod
    def _callback_is_allowed(callback: CallbackQuery) -> bool:
        data = callback.data or ""
        if data in ALLOWED_GROUP_CALLBACKS:
            return True
        return data.startswith(("profile:", "attack:"))
