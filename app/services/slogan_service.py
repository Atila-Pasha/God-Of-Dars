"""One durable, per-player slogan reward per cooldown window."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_logic import GameConfig, game_config
from app.models.resource import Resource
from app.repositories.user import UserRepository
from app.services.resource_service import ResourceService
from app.services.school_errors import SchoolUserNotFound
from app.services.user_service import UserInactiveError


@dataclass(frozen=True)
class SloganClaim:
    reward_banana: int
    retry_after_seconds: int = 0

    @property
    def awarded(self) -> bool:
        return self.retry_after_seconds == 0


class SloganService:
    def __init__(
        self,
        repository: UserRepository | None = None,
        *,
        config: GameConfig | None = None,
    ) -> None:
        self.repository = repository or UserRepository()
        self.config = config or game_config

    async def claim(
        self,
        session: AsyncSession,
        telegram_user_id: int,
        *,
        now: datetime | None = None,
    ) -> SloganClaim:
        # The user row is the serialization point for claims from multiple chats.
        user = await self.repository.get_by_telegram_user_id(
            session, telegram_user_id, for_update=True
        )
        if user is None:
            raise SchoolUserNotFound
        if not user.is_active:
            raise UserInactiveError
        now = now or datetime.now(UTC)
        last = user.last_slogan_at
        if last is not None:
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            remaining = (
                last + timedelta(seconds=self.config.slogan_cooldown_seconds) - now
            ).total_seconds()
            if remaining > 0:
                return SloganClaim(
                    reward_banana=self.config.slogan_reward_banana,
                    retry_after_seconds=ceil(remaining),
                )

        if user.resources is None:
            user.resources = Resource(coin=0, diamond=0, banana=0)
            await session.flush()
        await ResourceService.credit_banana(
            session,
            user.resources,
            user_id=user.id,
            amount=self.config.slogan_reward_banana,
            reason="SLOGAN_REWARD",
            reference_type="USER",
            reference_id=user.id,
        )
        user.last_slogan_at = now
        await session.flush()
        return SloganClaim(reward_banana=self.config.slogan_reward_banana)
