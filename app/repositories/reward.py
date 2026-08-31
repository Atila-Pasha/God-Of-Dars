from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reward import Reward


class RewardRepository:
    async def get_by_reference(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        source: str,
        reference_type: str,
        reference_id: int,
        for_update: bool = False,
    ) -> Reward | None:
        statement = select(Reward).where(
            Reward.user_id == user_id,
            Reward.source == source,
            Reward.reference_type == reference_type,
            Reward.reference_id == reference_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        return result.scalar_one_or_none()
