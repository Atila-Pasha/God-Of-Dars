import logging
from collections.abc import Iterable

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

VALID_MEMBER_STATUSES = frozenset({"creator", "administrator", "member"})


class MembershipCheckError(RuntimeError):
    """Raised when Telegram membership status cannot be checked safely."""


class SubscriptionService:
    def __init__(self, channels: str | Iterable[str] | None = None) -> None:
        if isinstance(channels, str):
            channels = (channels,)
        self.channels = tuple(
            channel.strip() for channel in (channels or ()) if channel.strip()
        )

    @property
    def channels_label(self) -> str:
        return ", ".join(self.channels)

    def set_channels(self, channels: Iterable[str] | None) -> None:
        self.channels = tuple(channel.strip() for channel in (channels or ()) if channel.strip())

    @staticmethod
    def channel_url(channel: str) -> str:
        return f"https://t.me/{channel.lstrip('@')}"

    @staticmethod
    def telegram_chat_id(channel: str) -> str:
        """Return the exact Bot API form for a stored channel identifier.

        Telegram accepts public channel usernames only as ``@username``.
        Numeric channel IDs (normally ``-100...``) must remain numeric strings.
        This also fixes legacy rows where the admin panel stored usernames
        without the leading ``@``.
        """
        value = str(channel).strip()
        if value.startswith("-") and value[1:].isdigit():
            return value
        if value.isdigit():
            return value
        return value if value.startswith("@") else f"@{value}"

    async def is_member(self, bot: Bot, telegram_user_id: int) -> bool:
        for channel in self.channels:
            chat_id = self.telegram_chat_id(channel)
            try:
                member = await bot.get_chat_member(
                    chat_id=chat_id,
                    user_id=telegram_user_id,
                )
            except TelegramAPIError as exc:
                logger.error(
                    "Telegram membership check failed for user %s in %s: %s",
                    telegram_user_id,
                    chat_id,
                    exc,
                )
                raise MembershipCheckError from exc
            except Exception as exc:
                logger.exception(
                    "Unexpected membership check failure for user %s in %s",
                    telegram_user_id,
                    channel,
                )
                raise MembershipCheckError from exc

            if member.status not in VALID_MEMBER_STATUSES:
                return False

        return True
