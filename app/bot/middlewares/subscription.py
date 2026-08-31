from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot.keyboards.start import join_channel_keyboard
from app.core.config import settings
from app.services.subscription_service import SubscriptionService

subscription_service = SubscriptionService(settings.required_channel_list)

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
            return await handler(event, data)

        try:
            is_member = await subscription_service.is_member(bot, telegram_user.id)
        except Exception:  # noqa: BLE001 - membership failures are user-safe
            return await self._show_error(event)

        if is_member:
            return await handler(event, data)
        return await self._show_join_prompt(event)

    @staticmethod
    def _is_bypassed(event: TelegramObject) -> bool:
        if isinstance(event, Message):
            if not event.text:
                return False
            command = event.text.split(maxsplit=1)[0].split("@", maxsplit=1)[0]
            return command == "/start"
        if isinstance(event, CallbackQuery):
            return bool(event.data and event.data.startswith("channel:"))
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
