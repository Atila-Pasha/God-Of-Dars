from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import QuestionScope, QuestionStatus, ResourceType
from app.models.answer import Answer
from app.models.group_question import GroupQuestion
from app.models.question import Question
from app.models.reward import Reward
from app.repositories.question import QuestionRepository
from app.services.library_errors import (
    DuplicateAnswer,
    GroupNotFound,
    InvalidAnswer,
    InvalidQuestion,
    QuestionAlreadyAnswered,
    QuestionExpired,
    QuestionNotFound,
    WrongGroup,
)
from app.services.reward_service import RewardService, RewardSpec


@dataclass(frozen=True)
class AnswerResult:
    answer: Answer
    correct: bool
    valid: bool
    rewards: tuple[Reward, ...] = ()

    @property
    def reward(self) -> Reward | None:
        """Backward-compatible access to the first reward, if there is one."""
        return self.rewards[0] if self.rewards else None

    @property
    def is_correct(self) -> bool:
        return self.correct

    @property
    def is_valid(self) -> bool:
        return self.valid


class QuestionService:
    """Application service for daily and group question workflows.

    The caller owns the surrounding transaction.  The service flushes writes
    so generated IDs and database constraints are available before the caller
    commits.  Row locks make the winner decision serializable on PostgreSQL.
    """

    def __init__(
        self,
        repository: QuestionRepository | None = None,
        *,
        reward_service: RewardService | None = None,
        daily_reward: RewardSpec | None = None,
        group_reward: RewardSpec | None = None,
    ) -> None:
        self.repository = repository or QuestionRepository()
        self.reward_service = reward_service or RewardService()
        self.daily_reward = daily_reward
        self.group_reward = group_reward

    async def create_question(
        self,
        session: AsyncSession,
        *,
        question_text: str,
        correct_answer: str,
        scope: QuestionScope = QuestionScope.DAILY,
        expires_at: datetime | None = None,
        published_at: datetime | None = None,
        coin_reward: int = 0,
        diamond_reward: int = 0,
        banana_reward: int = 0,
    ) -> Question:
        scope = self._scope(scope)
        self._validate_content(question_text, correct_answer)
        rewards = self._validate_rewards(
            coin_reward=coin_reward,
            diamond_reward=diamond_reward,
            banana_reward=banana_reward,
        )
        return await self.repository.create_question(
            session,
            question_text=question_text.strip(),
            correct_answer=correct_answer.strip(),
            scope=scope,
            expires_at=expires_at,
            published_at=published_at,
            **rewards,
        )

    async def create_daily_question(
        self,
        session: AsyncSession,
        *,
        question_text: str,
        correct_answer: str,
        expires_at: datetime | None = None,
        coin_reward: int = 0,
        diamond_reward: int = 0,
        banana_reward: int = 0,
    ) -> Question:
        return await self.create_question(
            session,
            question_text=question_text,
            correct_answer=correct_answer,
            scope=QuestionScope.DAILY,
            expires_at=expires_at,
            coin_reward=coin_reward,
            diamond_reward=diamond_reward,
            banana_reward=banana_reward,
        )

    async def create_group_question(
        self,
        session: AsyncSession,
        *,
        question_text: str,
        correct_answer: str,
        group_id: int,
        expires_at: datetime | None = None,
        published_at: datetime | None = None,
        coin_reward: int = 0,
        diamond_reward: int = 0,
        banana_reward: int = 0,
    ) -> GroupQuestion:
        group = await self.repository.get_group(session, group_id)
        if group is None or not group.is_active:
            raise GroupNotFound
        question = await self.create_question(
            session,
            question_text=question_text,
            correct_answer=correct_answer,
            scope=QuestionScope.GROUP,
            expires_at=expires_at,
            published_at=published_at,
            coin_reward=coin_reward,
            diamond_reward=diamond_reward,
            banana_reward=banana_reward,
        )
        return await self.repository.create_group_question(
            session,
            question=question,
            group=group,
            expires_at=expires_at,
            published_at=published_at,
        )

    async def create_group_question_for_all(
        self,
        session: AsyncSession,
        *,
        question_text: str,
        correct_answer: str,
        expires_at: datetime | None = None,
        published_at: datetime | None = None,
        coin_reward: int = 0,
        diamond_reward: int = 0,
        banana_reward: int = 0,
    ) -> list[GroupQuestion]:
        """Create one question and publish an independent copy to every group."""
        groups = await self.repository.list_active_groups(session)
        if not groups:
            raise GroupNotFound

        question = await self.create_question(
            session,
            question_text=question_text,
            correct_answer=correct_answer,
            scope=QuestionScope.GROUP,
            expires_at=expires_at,
            published_at=published_at,
            coin_reward=coin_reward,
            diamond_reward=diamond_reward,
            banana_reward=banana_reward,
        )
        return [
            await self.repository.create_group_question(
                session,
                question=question,
                group=group,
                expires_at=expires_at,
                published_at=published_at,
            )
            for group in groups
        ]

    async def publish_group_question(
        self,
        session: AsyncSession,
        *,
        question_id: int,
        group_id: int,
        expires_at: datetime | None = None,
        published_at: datetime | None = None,
    ) -> GroupQuestion:
        question = await self.repository.get_by_id(session, question_id)
        if question is None:
            raise QuestionNotFound
        self._validate_question(question, expected_scope=QuestionScope.GROUP)
        group = await self.repository.get_group(session, group_id)
        if group is None or not group.is_active:
            raise GroupNotFound
        return await self.repository.create_group_question(
            session,
            question=question,
            group=group,
            expires_at=question.expires_at if expires_at is None else expires_at,
            published_at=published_at,
        )

    async def get_active_daily_question(
        self, session: AsyncSession, *, now: datetime | None = None
    ) -> Question | None:
        return await self.repository.get_active_daily(
            session, now=self._now(now)
        )

    async def get_active_group_question_for_chat(
        self,
        session: AsyncSession,
        *,
        telegram_chat_id: int,
        now: datetime | None = None,
    ) -> GroupQuestion | None:
        return await self.repository.get_active_group_question_for_chat(
            session,
            telegram_chat_id=telegram_chat_id,
            now=self._now(now),
        )

    async def get_group_question_by_message(
        self,
        session: AsyncSession,
        *,
        telegram_chat_id: int,
        telegram_message_id: int,
    ) -> GroupQuestion | None:
        return await self.repository.get_group_question_by_message(
            session,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
        )

    async def first_group_answer(
        self, session: AsyncSession, group_question_id: int
    ) -> Answer | None:
        return await self.repository.get_first_group_answer(session, group_question_id)

    async def answer_daily_question(
        self,
        session: AsyncSession,
        user_id: int,
        question_id: int,
        answer_content: str,
        *,
        now: datetime | None = None,
    ) -> AnswerResult:
        if not answer_content or not answer_content.strip():
            raise InvalidAnswer
        current_time = self._now(now)
        question = await self.repository.get_by_id(
            session, question_id, for_update=True
        )
        if question is None:
            raise QuestionNotFound
        self._validate_question(question, expected_scope=QuestionScope.DAILY)

        if await self.repository.get_daily_answer(
            session, question_id=question_id, user_id=user_id, for_update=True
        ):
            raise DuplicateAnswer
        try:
            self._ensure_answerable(question.status, question.expires_at, current_time)
        except QuestionExpired:
            if question.status == QuestionStatus.ACTIVE:
                question.status = QuestionStatus.EXPIRED
                await session.flush()
            raise

        correct = self._matches(answer_content, question.correct_answer)
        answer = Answer(
            user_id=user_id,
            question_id=question.id,
            answer_content=answer_content.strip(),
            is_correct=correct,
            is_valid=correct,
        )
        session.add(answer)
        await session.flush()

        rewards: tuple[Reward, ...] = ()
        if correct:
            rewards = await self._grant_question_rewards(
                session,
                user_id=user_id,
                question=question,
                fallback=self.daily_reward,
                source="DAILY_QUESTION",
                reference_id=answer.id,
            )
        await session.flush()
        return AnswerResult(answer, correct=correct, valid=correct, rewards=rewards)

    async def answer_group_question(
        self,
        session: AsyncSession,
        user_id: int,
        question_id: int,
        group_id: int,
        answer_content: str,
        *,
        now: datetime | None = None,
    ) -> AnswerResult:
        if not answer_content or not answer_content.strip():
            raise InvalidAnswer
        current_time = self._now(now)
        publication = await self.repository.get_group_question(
            session,
            question_id=question_id,
            group_id=group_id,
            for_update=True,
        )
        if publication is None:
            raise WrongGroup
        question = publication.question
        self._validate_question(question, expected_scope=QuestionScope.GROUP)

        if await self.repository.get_group_answer(
            session,
            question_id=question_id,
            group_id=group_id,
            user_id=user_id,
            for_update=True,
        ):
            raise DuplicateAnswer
        expiration = publication.expires_at or question.expires_at
        try:
            self._ensure_answerable(publication.status, expiration, current_time)
        except QuestionExpired:
            if publication.status == QuestionStatus.ACTIVE:
                publication.status = QuestionStatus.EXPIRED
                if not await self.repository.has_active_group_publications(
                    session, question_id=question_id, exclude_id=publication.id
                ):
                    question.status = QuestionStatus.EXPIRED
                await session.flush()
            raise

        correct = self._matches(answer_content, question.correct_answer)
        answer = Answer(
            user_id=user_id,
            question_id=question_id,
            group_id=group_id,
            group_question_id=publication.id,
            answer_content=answer_content.strip(),
            is_correct=correct,
            is_valid=correct,
        )
        session.add(answer)
        await session.flush()

        rewards: tuple[Reward, ...] = ()
        # An incorrect attempt must not consume the group question.  The
        # publication is closed only after a correct answer wins.
        if correct:
            publication.status = QuestionStatus.ANSWERED
            publication.answered_at = current_time
            if not await self.repository.has_active_group_publications(
                session, question_id=question_id, exclude_id=publication.id
            ):
                question.status = QuestionStatus.ANSWERED
            rewards = await self._grant_question_rewards(
                session,
                user_id=user_id,
                question=question,
                fallback=self.group_reward,
                source="GROUP_QUESTION",
                reference_id=answer.id,
            )
        await session.flush()
        return AnswerResult(answer, correct=correct, valid=correct, rewards=rewards)

    async def submit_answer(
        self,
        session: AsyncSession,
        user_id: int,
        question_id: int,
        answer_content: str,
        *,
        group_id: int | None = None,
        now: datetime | None = None,
    ) -> AnswerResult:
        if group_id is None:
            return await self.answer_daily_question(
                session, user_id, question_id, answer_content, now=now
            )
        return await self.answer_group_question(
            session, user_id, question_id, group_id, answer_content, now=now
        )

    # Common short aliases keep the domain API convenient for future handlers.
    answer = submit_answer
    submit_daily_answer = answer_daily_question
    submit_group_answer = answer_group_question

    @staticmethod
    def _scope(scope: QuestionScope | str) -> QuestionScope:
        try:
            return scope if isinstance(scope, QuestionScope) else QuestionScope(scope)
        except (TypeError, ValueError) as exc:
            raise InvalidQuestion from exc

    @staticmethod
    def _validate_content(question_text: str, correct_answer: str) -> None:
        if not isinstance(question_text, str) or not question_text.strip():
            raise InvalidQuestion
        if not isinstance(correct_answer, str) or not correct_answer.strip():
            raise InvalidQuestion

    @staticmethod
    def _validate_rewards(
        *, coin_reward: int | None, diamond_reward: int | None, banana_reward: int | None
    ) -> dict[str, int]:
        if banana_reward not in (None, 0):
            raise InvalidQuestion
        values = {
            "coin_reward": coin_reward,
            "diamond_reward": diamond_reward,
            "banana_reward": 0,
        }
        for name, amount in values.items():
            if amount is None:
                values[name] = 0
            elif isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                raise InvalidQuestion
        return values

    async def _grant_question_rewards(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        question: Question,
        fallback: RewardSpec | None,
        source: str,
        reference_id: int,
    ) -> tuple[Reward, ...]:
        configured = tuple(
            RewardSpec(resource_type, amount)
            for resource_type, amount in (
                (ResourceType.COIN, getattr(question, "coin_reward", 0) or 0),
                (ResourceType.DIAMOND, getattr(question, "diamond_reward", 0) or 0),
            )
            if amount > 0
        )
        specs = configured or ((fallback,) if fallback is not None else ())
        rewards: list[Reward] = []
        for spec in specs:
            reward_result = await self.reward_service.grant(
                session,
                user_id=user_id,
                spec=spec,
                source=source,
                reference_type="ANSWER",
                reference_id=reference_id,
            )
            if reward_result is not None:
                rewards.append(reward_result.reward)
        return tuple(rewards)

    @staticmethod
    def _validate_question(
        question: Question, *, expected_scope: QuestionScope
    ) -> None:
        if question.scope != expected_scope:
            raise InvalidQuestion
        QuestionService._validate_content(
            question.question_text, question.correct_answer
        )

    @staticmethod
    def _ensure_answerable(
        status: QuestionStatus,
        expires_at: datetime | None,
        now: datetime,
    ) -> None:
        if status == QuestionStatus.ANSWERED:
            raise QuestionAlreadyAnswered
        if status == QuestionStatus.EXPIRED:
            raise QuestionExpired
        if status != QuestionStatus.ACTIVE:
            raise InvalidQuestion
        if expires_at is not None:
            expiration = (
                expires_at.replace(tzinfo=UTC)
                if expires_at.tzinfo is None
                else expires_at
            )
            if expiration <= now:
                raise QuestionExpired

    @staticmethod
    def _matches(answer: str, correct_answer: str) -> bool:
        return answer.strip().casefold() == correct_answer.strip().casefold()

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(UTC)
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value
