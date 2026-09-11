from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.dependencies import AuthenticatedUser, DatabaseSession
from app.api.errors import APIError
from app.api.presenters import mine, resources, study_session, study_state
from app.api.responses import idempotent_response
from app.api.schemas.domain import (
    DailyAnswerRequest,
    DailyAnswerView,
    DailyQuestionView,
    DailyQuestView,
    MineCollectView,
    MineView,
    ResourceBalances,
    StudyPackView,
    StudyStartRequest,
    StudyStateView,
)
from app.models.answer import Answer
from app.models.daily_quest import DailyQuestProgress
from app.models.resource import Resource
from app.services.daily_quest_service import DailyQuestService
from app.services.mine_service import MineService
from app.services.question_service import QuestionService
from app.services.study_service import StudyService
from app.services.subscription_service import MembershipCheckError, SubscriptionService

router = APIRouter(tags=["activities"])
mines = MineService()
studies = StudyService()
questions = QuestionService()
quests = DailyQuestService()


@router.get("/me/mine", response_model=MineView)
async def my_mine(current: AuthenticatedUser, session: DatabaseSession) -> MineView:
    return mine(
        await mines.open(session, current.user.id), player_level=current.user.level
    )


@router.post("/me/mine/collect", response_model=MineCollectView)
async def collect_mine(
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> MineCollectView:
        snapshot, amounts = await mines.collect(session, current.user.id)
        balance = await session.scalar(
            select(Resource).where(Resource.user_id == current.user.id)
        )
        return MineCollectView(
            mine=mine(snapshot, player_level=current.user.level),
            collected=ResourceBalances(
                coin=amounts[0], diamond=amounts[1], banana=amounts[2]
            ),
            balances=resources(balance),
        )

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="mine.collect",
        key=idempotency_key,
        payload={},
        action=action,
    )


@router.post("/me/mine/upgrade", response_model=MineView)
async def upgrade_mine(
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> MineView:
        snapshot = await mines.upgrade(session, current.user.id)
        return mine(snapshot, player_level=current.user.level)

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="mine.upgrade",
        key=idempotency_key,
        payload={},
        action=action,
    )


@router.get("/study/packs", response_model=list[StudyPackView])
async def study_packs(
    current: AuthenticatedUser, session: DatabaseSession
) -> list[StudyPackView]:
    del current
    return [
        StudyPackView(
            key=item.key,
            name=item.name,
            duration_minutes=item.duration_minutes,
            reward_resource=item.reward_resource,
            reward_amount=item.reward_amount,
        )
        for item in await studies.packs(session)
    ]


@router.get("/me/study", response_model=StudyStateView)
async def my_study(
    current: AuthenticatedUser, session: DatabaseSession
) -> StudyStateView:
    item = await studies.active(session, current.user.id, for_update=False)
    return study_state(item)


@router.post("/me/study/start", response_model=StudyStateView)
async def start_study(
    body: StudyStartRequest,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> StudyStateView:
        result = await studies.start(session, current.user.id, body.pack_key)
        return StudyStateView(
            active=study_session(result.study),
            settled_reward=(
                {result.completed_reward[0].value: result.completed_reward[1]}
                if result.completed_reward
                else None
            ),
        )

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="study.start",
        key=idempotency_key,
        payload=body.model_dump(mode="json"),
        action=action,
        status_code=201,
    )


@router.post("/me/study/settle", response_model=StudyStateView)
async def settle_study(
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> StudyStateView:
        item, reward = await studies.settle(session, current.user.id)
        return study_state(item, reward)

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="study.settle",
        key=idempotency_key,
        payload={},
        action=action,
    )


@router.get("/daily-question", response_model=DailyQuestionView | None)
async def daily_question(
    current: AuthenticatedUser, session: DatabaseSession
) -> DailyQuestionView | None:
    question = await questions.get_active_daily_question(session)
    if question is None:
        return None
    answered = await session.scalar(
        select(Answer.id).where(
            Answer.user_id == current.user.id,
            Answer.question_id == question.id,
            Answer.group_id.is_(None),
        )
    )
    return DailyQuestionView(
        id=question.id,
        question_text=question.question_text,
        expires_at=question.expires_at,
        rewards=ResourceBalances(
            coin=question.coin_reward,
            diamond=question.diamond_reward,
            banana=question.banana_reward,
        ),
        already_answered=answered is not None,
    )


@router.post("/daily-question/answer", response_model=DailyAnswerView)
async def answer_daily_question(
    body: DailyAnswerRequest,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> DailyAnswerView:
        result = await questions.answer_daily_question(
            session,
            current.user.id,
            body.question_id,
            body.answer,
        )
        balance = await session.scalar(
            select(Resource).where(Resource.user_id == current.user.id)
        )
        reward_values = {"COIN": 0, "DIAMOND": 0, "BANANA": 0}
        for reward in result.rewards:
            reward_values[reward.resource_type.value] += reward.amount
        return DailyAnswerView(
            answer_id=result.answer.id,
            correct=result.correct,
            rewards=ResourceBalances(
                coin=reward_values["COIN"],
                diamond=reward_values["DIAMOND"],
                banana=reward_values["BANANA"],
            ),
            balances=resources(balance),
        )

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="daily-question.answer",
        key=idempotency_key,
        payload=body.model_dump(mode="json"),
        action=action,
    )


@router.get("/me/daily-quests", response_model=list[DailyQuestView])
async def daily_quests(
    current: AuthenticatedUser, session: DatabaseSession
) -> list[DailyQuestView]:
    today = quests.today()
    items = await quests.list(session, today, active_only=True)
    result = []
    for item in items:
        progress = await session.scalar(
            select(DailyQuestProgress).where(
                DailyQuestProgress.user_id == current.user.id,
                DailyQuestProgress.quest_id == item.id,
            )
        )
        progress_value = progress.progress if progress else 0
        result.append(
            DailyQuestView(
                id=item.id,
                activity_date=item.activity_date,
                quest_type=item.quest_type,
                title=item.title,
                description=item.description,
                target=item.target,
                progress_id=progress.id if progress else None,
                progress=progress_value,
                completed=progress_value >= item.target,
                claimed=progress.claimed if progress else False,
                rewards=item.rewards or {},
                metadata=item.quest_metadata or {},
            )
        )
    return result


@router.post("/me/daily-quests/{progress_id}/claim", response_model=DailyQuestView)
async def claim_daily_quest(
    progress_id: int,
    request: Request,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    membership_verified: bool | None = None
    current_progress = await session.scalar(
        select(DailyQuestProgress).where(
            DailyQuestProgress.id == progress_id,
            DailyQuestProgress.user_id == current.user.id,
        )
    )
    current_quest = (
        await quests.repository.get(session, current_progress.quest_id)
        if current_progress
        else None
    )
    if current_quest is not None and current_quest.quest_type == "JOIN_CHANNEL":
        channel = (current_quest.quest_metadata or {}).get("channel")
        if not isinstance(channel, str):
            raise APIError(409, "QUEST_NOT_CLAIMABLE", "کانال مأموریت معتبر نیست.")
        try:
            identifier, _ = SubscriptionService.parse_daily_channel(channel)
        except ValueError as exc:
            raise APIError(
                409, "QUEST_NOT_CLAIMABLE", "کانال مأموریت معتبر نیست."
            ) from exc
        await session.commit()
        subscription: SubscriptionService = request.app.state.subscription_service
        try:
            membership_verified = await subscription.is_member_in_channel(
                request.app.state.telegram_bot,
                current.user.telegram_user_id,
                identifier,
            )
        except MembershipCheckError as exc:
            raise APIError(
                503,
                "TELEGRAM_MEMBERSHIP_UNAVAILABLE",
                "بررسی عضویت تلگرام موقتاً ممکن نیست.",
            ) from exc

    async def action() -> DailyQuestView:
        async def membership_checker(channel: str) -> bool:
            del channel
            return bool(membership_verified)

        progress = await quests.claim(
            session,
            user_id=current.user.id,
            progress_id=progress_id,
            membership_checker=membership_checker,
        )
        if progress is None:
            raise APIError(409, "QUEST_NOT_CLAIMABLE", "این مأموریت قابل دریافت نیست.")
        item = await quests.repository.get(session, progress.quest_id)
        if item is None:
            raise APIError(409, "QUEST_NOT_CLAIMABLE", "این مأموریت قابل دریافت نیست.")
        return DailyQuestView(
            id=item.id,
            activity_date=item.activity_date,
            quest_type=item.quest_type,
            title=item.title,
            description=item.description,
            target=item.target,
            progress_id=progress.id,
            progress=progress.progress,
            completed=progress.progress >= item.target,
            claimed=progress.claimed,
            rewards=item.rewards or {},
            metadata=item.quest_metadata or {},
        )

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="daily-quest.claim",
        key=idempotency_key,
        payload={"progress_id": progress_id},
        action=action,
    )
