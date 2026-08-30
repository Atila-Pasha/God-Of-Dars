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

    @staticmethod
    def channel_url(channel: str) -> str:
        return f"https://t.me/{channel.lstrip('@')}"

    async def is_member(self, bot: Bot, telegram_user_id: int) -> bool:
        for channel in self.channels:
            try:
                member = await bot.get_chat_member(
                    chat_id=channel,
                    user_id=telegram_user_id,
                )
            except TelegramAPIError as exc:
                logger.error(
                    "Telegram membership check failed for user %s in %s: %s",
                    telegram_user_id,
                    channel,
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
