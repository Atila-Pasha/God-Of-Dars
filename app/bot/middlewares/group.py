from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMemberUpdated,
    Message,
    TelegramObject,
)
from aiogram.types import User as TelegramUser
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.custom_emojis import reset_group_reply_context, set_group_reply_context
from app.bot.keyboards.main_menu import MENU_SECTION_LABELS
from app.core.config import settings
from app.services.group_service import GroupService
from app.services.user_service import (
    UserInactiveError,
    UserInitializationError,
    UserService,
)

logger = logging.getLogger(__name__)

GROUP_CHAT_TYPES = frozenset({"group", "supergroup"})
ALLOWED_GROUP_COMMANDS = frozenset(
    {
        "help",
        "stat",
        "attack",
        "profile_info",
        "war",
        "assets",
        "knowledge",
    }
)
ALLOWED_GROUP_CALLBACKS = frozenset({"library:group", "library:cancel"})


class GroupAccessMiddleware(BaseMiddleware):
    """Register groups and keep private-only bot features out of group chats."""

    def __init__(
        self,
        group_service: GroupService | None = None,
        user_service: UserService | None = None,
    ) -> None:
        self.group_service = group_service or GroupService()
        self.user_service = user_service or UserService()
        self._registered_groups: dict[int, float] = {}
        self._registered_users: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and self._is_group_message(event):
            replied_user = (
                event.reply_to_message.from_user
                if event.reply_to_message is not None
                else None
            )
            await self._register_users(
                data.get("session"),
                event.from_user,
                replied_user,
                event.left_chat_member,
                *(event.new_chat_members or ()),
            )
            await self._register_group(event, data.get("session"))
            if not self._message_is_allowed(event):
                # Keep groups quiet for private-menu input and unsupported
                # commands; a warning for each input only creates spam.
                return None
            token = set_group_reply_context(event.chat.id, event.message_id)
            try:
                return await handler(event, data)
            finally:
                reset_group_reply_context(token)
        elif isinstance(event, CallbackQuery) and self._is_group_callback(event):
            if not self._callback_is_allowed(event):
                return None
            if event.message is None:
                return None
            token = set_group_reply_context(
                event.message.chat.id, event.message.message_id
            )
            try:
                return await handler(event, data)
            finally:
                reset_group_reply_context(token)
        elif (
            isinstance(event, ChatMemberUpdated) and event.chat.type in GROUP_CHAT_TYPES
        ):
            session = data.get("session")
            await self._register_users(
                session,
                event.from_user,
                event.new_chat_member.user,
            )
            await self._register_chat(event.chat, session)
        return await handler(event, data)

    async def _register_group(
        self, message: Message, session: AsyncSession | None
    ) -> None:
        await self._register_chat(message.chat, session)

    async def _register_chat(self, chat: Chat, session: AsyncSession | None) -> None:
        if session is None:
            return
        now = monotonic()
        if self._is_cached(self._registered_groups, chat.id, now):
            return
        title = chat.title or chat.username or "گروه بدون نام"
        try:
            # A registration failure is non-critical, but it must not poison
            # the transaction used by the actual update handler.
            async with session.begin_nested():
                await self.group_service.register_chat(
                    session,
                    telegram_chat_id=chat.id,
                    title=title,
                    username=chat.username,
                )
            self._remember(
                self._registered_groups,
                chat.id,
                now + settings.GROUP_REGISTER_CACHE_TTL,
                settings.GROUP_REGISTER_CACHE_MAX_ENTRIES,
            )
        except SQLAlchemyError:
            logger.exception("Could not register Telegram group %s", chat.id)

    async def _register_users(
        self,
        session: AsyncSession | None,
        *telegram_users: TelegramUser | None,
    ) -> None:
        if session is None:
            return
        now = monotonic()
        seen: set[int] = set()
        for telegram_user in telegram_users:
            if (
                telegram_user is None
                or telegram_user.is_bot
                or telegram_user.id in seen
            ):
                continue
            seen.add(telegram_user.id)
            if self._is_cached(self._registered_users, telegram_user.id, now):
                continue
            try:
                user = await self.user_service.get_or_create_from_telegram(
                    session, telegram_user
                )
                # A newly created row is not durable until the outer middleware
                # commits. Cache it only after a later update observes it.
                if not getattr(user, "_was_created", False):
                    self._remember(
                        self._registered_users,
                        telegram_user.id,
                        now + settings.GROUP_USER_CACHE_TTL,
                        settings.GROUP_USER_CACHE_MAX_ENTRIES,
                    )
            except UserInactiveError:
                # Observing a banned member must never reactivate the account.
                continue
            except UserInitializationError:
                logger.exception(
                    "Could not auto-register Telegram group member %s",
                    telegram_user.id,
                )

    @staticmethod
    def _is_cached(cache: dict[int, float], key: int, now: float) -> bool:
        expires_at = cache.get(key, 0)
        if expires_at > now:
            return True
        cache.pop(key, None)
        return False

    @staticmethod
    def _remember(
        cache: dict[int, float],
        key: int,
        expires_at: float,
        max_entries: int,
    ) -> None:
        # Dicts preserve insertion order, giving us a low-cost bounded cache.
        cache.pop(key, None)
        while len(cache) >= max_entries:
            cache.pop(next(iter(cache)))
        cache[key] = expires_at

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
        # Attack is intentionally a plain-text group action. Keep it explicit
        # here so future group restrictions cannot silently swallow it.
        if text.startswith(("حمله", "خرید", "اطلاعات", "معرفی")):
            return True
        if text.startswith("/"):
            command = text.split(maxsplit=1)[0].split("@", maxsplit=1)[0]
            return command.removeprefix("/").casefold() in ALLOWED_GROUP_COMMANDS
        return text not in MENU_SECTION_LABELS

    @staticmethod
    def _callback_is_allowed(callback: CallbackQuery) -> bool:
        data = callback.data or ""
        if data in ALLOWED_GROUP_CALLBACKS:
            return True
        return data.startswith(
            (
                "help:",
                "profile:",
                "attack:",
                "confirm:",
                "shield_purchase:",
                "chance_box:",
                "library:",
                "library_teacher:",
            )
        )
