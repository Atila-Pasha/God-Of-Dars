from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_quest import DailyQuest, DailyQuestProgress


class DailyQuestRepository:
    async def list_for_date(self, session: AsyncSession, activity_date: date, *, active_only: bool = True):
        query = select(DailyQuest).where(DailyQuest.activity_date == activity_date)
        if active_only:
            query = query.where(DailyQuest.is_active.is_(True))
        return list((await session.scalars(query.order_by(DailyQuest.id))).all())

    async def get(self, session: AsyncSession, quest_id: int, *, for_update: bool = False):
        query = select(DailyQuest).where(DailyQuest.id == quest_id)
        if for_update:
            query = query.with_for_update()
        return await session.scalar(query)

    async def progress(self, session: AsyncSession, user_id: int, quest_id: int, *, for_update: bool = False):
        query = select(DailyQuestProgress).where(DailyQuestProgress.user_id == user_id, DailyQuestProgress.quest_id == quest_id)
        if for_update:
            query = query.with_for_update()
        return await session.scalar(query)
