import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot.keyboards.start import join_channel_keyboard
from app.core.config import settings
from app.repositories.bot_settings import BotSettingsRepository
from app.services.subscription_service import SubscriptionService

subscription_service = SubscriptionService()
settings_repository = BotSettingsRepository()
_channels_cache: tuple[float, tuple[str, ...]] = (0.0, ())
_channels_cache_lock = asyncio.Lock()


def invalidate_channels_cache() -> None:
    """Make an admin channel change visible on the next update."""
    global _channels_cache
    _channels_cache = (0.0, ())


async def refresh_channels(session, *, force: bool = False) -> tuple[str, ...]:
    global _channels_cache
    now = monotonic()
    if not force and _channels_cache[0] > now:
        return _channels_cache[1]
    async with _channels_cache_lock:
        if not force and _channels_cache[0] > monotonic():
            return _channels_cache[1]
        channels = await settings_repository.list_channels(session)
        stored = await settings_repository.get(session)
        values = []
        identifiers = [
            str(item.telegram_id or item.username or "") for item in channels
        ]
        if stored.is_active and (
            stored.required_channel_telegram_id or stored.required_channel_username
        ):
            identifiers.append(
                str(
                    stored.required_channel_telegram_id
                    or stored.required_channel_username
                )
            )
        for identifier in identifiers:
            if not SubscriptionService.is_valid_channel_identifier(identifier):
                # A malformed active lock must never silently unlock the bot.
                raise ValueError("Invalid required channel configuration")
            values.append(SubscriptionService.normalize_channel_identifier(identifier))
        normalized = tuple(dict.fromkeys(values))
        subscription_service.set_channels(normalized)
        _channels_cache = (monotonic() + settings.CHANNELS_CACHE_TTL, normalized)
        return normalized


JOIN_MESSAGE = (
    "برای استفاده از ربات، ابتدا باید عضو کانال‌های زیر شوید:\n\n"
    "پس از عضویت، روی «بررسی عضویت» بزنید."
)
MEMBERSHIP_ERROR_MESSAGE = (
    "در حال حاضر بررسی عضویت امکان‌پذیر نیست. لطفاً کمی بعد دوباره تلاش کنید."
)


class SubscriptionMiddleware(BaseMiddleware):
    """Require channel membership before every user-facing bot feature."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if self._is_bypassed(event):
            return await handler(event, data)

        telegram_user = getattr(event, "from_user", None)
        bot = getattr(event, "bot", None)
        if telegram_user is None or bot is None:
            return await self._show_error(event)

        try:
            session = data.get("session")
            if session is not None:
                await refresh_channels(session)
            is_member = await subscription_service.is_member(
                bot, telegram_user.id, force_refresh=True
            )
        except Exception:  # noqa: BLE001 - membership failures are user-safe
            return await self._show_error(event)

        if is_member:
            return await handler(event, data)
        return await self._show_join_prompt(event)

    @staticmethod
    def _is_bypassed(event: TelegramObject) -> bool:
        if isinstance(event, Message):
            return False
        if isinstance(event, CallbackQuery):
            # This exact handler verifies membership before initialization.
            return event.data == "channel:check"
        return True

    @staticmethod
    async def _show_join_prompt(event: TelegramObject) -> None:
        if isinstance(event, Message):
            try:
                await event.answer(
                    JOIN_MESSAGE,
                    reply_markup=join_channel_keyboard(subscription_service),
                )
            except TelegramAPIError:
                return
        elif isinstance(event, CallbackQuery):
            try:
                if event.message is not None:
                    await event.message.answer(
                        JOIN_MESSAGE,
                        reply_markup=join_channel_keyboard(subscription_service),
                    )
                await event.answer("ابتدا باید عضو کانال شوید.", show_alert=True)
            except TelegramAPIError:
                return

    @staticmethod
    async def _show_error(event: TelegramObject) -> None:
        if isinstance(event, Message):
            try:
                await event.answer(MEMBERSHIP_ERROR_MESSAGE)
            except TelegramAPIError:
                return
        elif isinstance(event, CallbackQuery):
            try:
                await event.answer(MEMBERSHIP_ERROR_MESSAGE, show_alert=True)
            except TelegramAPIError:
                return
