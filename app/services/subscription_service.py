import logging
from collections.abc import Iterable
from time import monotonic

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.core.config import settings

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
        self._membership_cache: dict[tuple[str, int], tuple[float, bool]] = {}
        self.membership_cache_ttl = settings.MEMBERSHIP_CACHE_TTL
        self.membership_cache_max_entries = settings.MEMBERSHIP_CACHE_MAX_ENTRIES

    @property
    def channels_label(self) -> str:
        return ", ".join(self.channels)

    def set_channels(self, channels: Iterable[str] | None) -> None:
        normalized = tuple(channel.strip() for channel in (channels or ()) if channel.strip())
        if normalized != self.channels:
            self.channels = normalized
            self._membership_cache.clear()

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

    async def is_member(
        self, bot: Bot, telegram_user_id: int, *, force_refresh: bool = False
    ) -> bool:
        cache_key = (str(getattr(bot, "token", "")), telegram_user_id)
        cached = self._membership_cache.get(cache_key)
        if not force_refresh and cached and cached[0] > monotonic():
            return cached[1]
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
                self._remember(cache_key, False)
                return False

        self._remember(cache_key, True)
        return True

    async def is_member_in_channel(self, bot: Bot, telegram_user_id: int, channel: str) -> bool:
        try:
            member = await bot.get_chat_member(
                chat_id=self.telegram_chat_id(channel), user_id=telegram_user_id
            )
        except Exception as exc:
            raise MembershipCheckError from exc
        return member.status in VALID_MEMBER_STATUSES

    def _remember(self, key: tuple[str, int], value: bool) -> None:
        if len(self._membership_cache) >= self.membership_cache_max_entries:
            now = monotonic()
            self._membership_cache = {
                item: entry for item, entry in self._membership_cache.items() if entry[0] > now
            }
            if len(self._membership_cache) >= self.membership_cache_max_entries:
                self._membership_cache.clear()
        self._membership_cache[key] = (monotonic() + self.membership_cache_ttl, value)
