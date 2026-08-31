from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class ReferralRepository:
    async def get_user_for_update(
        self, session: AsyncSession, user_id: int
    ) -> User | None:
        result = await session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def count_referrals(self, session: AsyncSession, referrer_id: int) -> int:
        result = await session.execute(
            select(func.count(User.id)).where(User.referrer_id == referrer_id)
        )
        return int(result.scalar_one())

    async def list_referrals(
        self, session: AsyncSession, referrer_id: int
    ) -> list[User]:
        result = await session.execute(
            select(User)
            .where(User.referrer_id == referrer_id)
            .order_by(User.id)
        )
        return list(result.scalars().all())

    async def is_descendant(
        self,
        session: AsyncSession,
        *,
        ancestor_id: int,
        descendant_id: int,
    ) -> bool:
        """Return whether descendant_id is anywhere below ancestor_id."""
        descendants = select(User.id).where(User.referrer_id == ancestor_id).cte(
            "referral_descendants", recursive=True
        )
        descendants = descendants.union_all(
            select(User.id).join(
                descendants, User.referrer_id == descendants.c.id
            )
        )
        result = await session.execute(
            select(exists(select(descendants.c.id).where(descendants.c.id == descendant_id)))
        )
        return bool(result.scalar_one())
