from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType
from app.core.game_logic import GameConfig, GameConfigurationError, game_config
from app.repositories.user import UserRepository
from app.services.resource_service import ResourceService
from app.services.school_errors import (
    InsufficientCoins,
    MaxLevelReached,
    OperationNotConfigured,
    ResourceNotFound,
    SchoolUserNotFound,
)


class LevelService:
    def __init__(self, *, config: GameConfig | None = None) -> None:
        self.config = config or game_config
        self.repository = UserRepository()

    def upgrade_cost(self, level: int) -> int:
        try:
            return self.config.level_progression.upgrade_cost(level)
        except GameConfigurationError as exc:
            raise OperationNotConfigured from exc

    async def upgrade(self, session: AsyncSession, user_id: int):
        user = await self.repository.get_by_id_for_update(session, user_id)
        if user is None:
            raise SchoolUserNotFound
        if user.level >= self.config.level_progression.max_level:
            raise MaxLevelReached
        resources = await self.repository.get_resources_for_update(session, user_id)
        if resources is None:
            raise ResourceNotFound
        cost = self.upgrade_cost(user.level)
        # BANANA is the persisted XP balance. It is earned only from attacks.
        # Reaching the threshold consumes the whole XP balance, as configured
        # by the game rule that XP resets after every level-up.
        if resources.banana < cost:
            raise InsufficientCoins
        amount = (
            resources.banana
            if self.config.level_progression.reset_xp_on_level_up
            else cost
        )
        ResourceService.debit(
            session,
            resources,
            user_id=user.id,
            resource_type=ResourceType.BANANA,
            amount=amount,
            reason="LEVEL_UPGRADE",
            reference_type="USER",
            reference_id=user.id,
        )
        user.level += 1
        await session.flush()
        return user
