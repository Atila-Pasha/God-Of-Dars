from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResourceType
from app.models.daily_quest import (
    QUEST_TYPES,
    DailyQuest,
    DailyQuestEvent,
    DailyQuestProgress,
)
from app.repositories.daily_quest import DailyQuestRepository
from app.services.reward_service import RewardService, RewardSpec


class DailyQuestService:
    def __init__(self, repository=None, reward_service=None):
        self.repository = repository or DailyQuestRepository()
        self.reward_service = reward_service or RewardService()

    @staticmethod
    def _date(value: date | datetime | None) -> date:
        if value is None:
            return datetime.now(UTC).date()
        return value.date() if isinstance(value, datetime) else value

    @staticmethod
    def _rewards(rewards: dict[str, int] | None) -> dict[str, int]:
        if rewards is None:
            return {}
        normalized: dict[str, int] = {}
        for key, value in rewards.items():
            resource = ResourceType(str(key).upper())
            if isinstance(value, bool) or int(value) < 0:
                raise ValueError("reward amounts must be non-negative integers")
            if int(value):
                normalized[resource.value] = int(value)
        return normalized

    @staticmethod
    def _validate_metadata(metadata: dict | None) -> dict:
        if metadata is None:
            return {}
        if not isinstance(metadata, dict):
            raise ValueError("quest metadata must be an object")
        return dict(metadata)

    async def create(
        self,
        session: AsyncSession,
        *,
        activity_date: date,
        quest_type: str,
        title: str,
        target: int,
        rewards: dict[str, int],
        description: str | None = None,
        metadata: dict | None = None,
        is_active: bool = True,
    ):
        if quest_type not in QUEST_TYPES or not title.strip() or target <= 0:
            raise ValueError("invalid daily quest")
        activity_date = self._date(activity_date)
        normalized = self._rewards(rewards)
        metadata = self._validate_metadata(metadata)
        if quest_type == "JOIN_CHANNEL" and not metadata.get("channel"):
            raise ValueError("JOIN_CHANNEL requires metadata.channel")
        quest = DailyQuest(
            activity_date=activity_date,
            quest_type=quest_type,
            title=title.strip(),
            description=description,
            target=target,
            rewards=normalized,
            quest_metadata=metadata,
            is_active=is_active,
        )
        session.add(quest)
        await session.flush()
        return quest

    async def update(self, session: AsyncSession, quest_id: int, **values):
        quest = await self.repository.get(session, quest_id, for_update=True)
        if quest is None:
            return None
        allowed = {"activity_date", "quest_type", "title", "description", "target",
                   "rewards", "quest_metadata", "is_active"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unsupported quest fields: {', '.join(sorted(unknown))}")
        if "activity_date" in values and values["activity_date"] is not None:
            quest.activity_date = self._date(values["activity_date"])
        if "quest_type" in values and values["quest_type"] is not None:
            if values["quest_type"] not in QUEST_TYPES:
                raise ValueError("invalid daily quest type")
            quest.quest_type = values["quest_type"]
        if "title" in values and values["title"] is not None:
            if not str(values["title"]).strip():
                raise ValueError("quest title is required")
            quest.title = str(values["title"]).strip()
        if "description" in values:
            quest.description = values["description"]
        if "target" in values and values["target"] is not None:
            if isinstance(values["target"], bool) or int(values["target"]) <= 0:
                raise ValueError("quest target must be positive")
            quest.target = int(values["target"])
        if "rewards" in values and values["rewards"] is not None:
            quest.rewards = self._rewards(values["rewards"])
        if "quest_metadata" in values and values["quest_metadata"] is not None:
            quest.quest_metadata = self._validate_metadata(values["quest_metadata"])
        if "is_active" in values and values["is_active"] is not None:
            quest.is_active = bool(values["is_active"])
        if quest.quest_type == "JOIN_CHANNEL" and not (quest.quest_metadata or {}).get("channel"):
            raise ValueError("JOIN_CHANNEL requires metadata.channel")
        await session.flush()
        return quest

    async def delete(self, session: AsyncSession, quest_id: int) -> bool:
        quest = await self.repository.get(session, quest_id, for_update=True)
        if quest is None:
            return False
        quest.is_active = False
        await session.flush()
        return True

    async def list(
        self, session: AsyncSession, activity_date: date, *, active_only: bool = False
    ):
        return await self.repository.list_for_date(
            session, activity_date, active_only=active_only
        )

    async def record_event(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        event_type: str,
        event_id: str,
        amount: int = 1,
        activity_date: date | None = None,
        event_metadata: dict | None = None,
    ) -> list[DailyQuestProgress]:
        if event_type not in QUEST_TYPES or amount <= 0:
            return []
        if not hasattr(session, "begin_nested"):
            return []
        day = activity_date or self._date(None)
        event = DailyQuestEvent(
            user_id=user_id, activity_date=day, event_key=f"{event_type}:{event_id}"
        )
        try:
            async with session.begin_nested():
                session.add(event)
                await session.flush()
        except IntegrityError:
            return []
        quests = await self.repository.list_for_date(session, day)
        changed = []
        for quest in quests:
            if quest.quest_type != event_type:
                continue
            if event_type == "JOIN_CHANNEL":
                configured_channel = (quest.quest_metadata or {}).get("channel")
                if configured_channel and configured_channel != (event_metadata or {}).get("channel"):
                    continue
            progress = await self.repository.progress(
                session, user_id, quest.id, for_update=True
            )
            if progress is None:
                progress = DailyQuestProgress(
                    user_id=user_id, quest_id=quest.id, activity_date=day
                )
                session.add(progress)
                await session.flush()
            if not progress.claimed:
                progress.progress = min(quest.target, progress.progress + amount)
                if progress.progress >= quest.target and progress.completed_at is None:
                    progress.completed_at = datetime.now(UTC)
                changed.append(progress)
        await session.flush()
        return changed

    async def claim(
        self, session: AsyncSession, *, user_id: int, progress_id: int,
        membership_checker=None,
    ):
        progress = await session.scalar(
            select(DailyQuestProgress)
            .where(DailyQuestProgress.id == progress_id)
            .with_for_update()
        )
        if progress is None or progress.user_id != user_id:
            return None
        quest = await self.repository.get(session, progress.quest_id, for_update=True)
        if quest is None or progress.claimed or progress.progress < quest.target:
            return None
        if quest.quest_type == "JOIN_CHANNEL" and membership_checker is not None:
            channel = (quest.quest_metadata or {}).get("channel")
            if not channel or not await membership_checker(channel):
                return None
        for resource, amount in (quest.rewards or {}).items():
            result = await self.reward_service.grant(
                session,
                user_id=user_id,
                spec=RewardSpec(ResourceType(resource), int(amount)),
                source="DAILY_QUEST",
                reference_type="QUEST",
                reference_id=progress.id,
            )
            if result is None:
                continue
        progress.claimed = True
        progress.claimed_at = datetime.now(UTC)
        await session.flush()
        return progress

    async def stats(self, session: AsyncSession, *, quest_id: int):
        quest = await self.repository.get(session, quest_id)
        if quest is None:
            return {"participants": 0, "completed": 0, "claimed": 0}
        rows = list(
            (
                await session.scalars(
                    select(DailyQuestProgress).where(
                        DailyQuestProgress.quest_id == quest_id
                    )
                )
            ).all()
        )
        return {
            "participants": len(rows),
            "completed": sum(p.progress >= quest.target for p in rows),
            "claimed": sum(p.claimed for p in rows),
        }
