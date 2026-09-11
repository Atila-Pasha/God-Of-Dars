from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from app.api.cursors import CursorCodec
from app.api.dependencies import AuthenticatedUser, DatabaseSession
from app.api.errors import APIError
from app.api.presenters import profile, resources, user_summary
from app.api.responses import idempotent_response
from app.api.schemas.domain import (
    LevelView,
    ProfileView,
    PublicProfileView,
    ResourceBalances,
    TransactionPage,
    TransactionView,
    UserSummary,
)
from app.core.game_logic import game_config
from app.models.resource import Resource
from app.models.transaction import Transaction
from app.models.user import User
from app.services.level_service import LevelService
from app.services.profile_service import ProfileNotFound, ProfileService

router = APIRouter(tags=["profile"])
profile_service = ProfileService()
level_service = LevelService()


@router.get("/me", response_model=UserSummary)
async def me(current: AuthenticatedUser) -> UserSummary:
    return user_summary(current.user)


@router.get("/me/profile", response_model=ProfileView)
async def my_profile(
    current: AuthenticatedUser, session: DatabaseSession
) -> ProfileView:
    snapshot = await profile_service.snapshot(session, current.user.id)
    return profile(snapshot)


@router.get("/me/resources", response_model=ResourceBalances)
async def my_resources(
    current: AuthenticatedUser, session: DatabaseSession
) -> ResourceBalances:
    value = await session.scalar(
        select(Resource).where(Resource.user_id == current.user.id)
    )
    return resources(value)


@router.get("/me/transactions", response_model=TransactionPage)
async def my_transactions(
    current: AuthenticatedUser,
    session: DatabaseSession,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> TransactionPage:
    before_id = CursorCodec.decode(cursor, resource="transactions")
    query = select(Transaction).where(Transaction.user_id == current.user.id)
    if before_id is not None:
        query = query.where(Transaction.id < before_id)
    rows = list(
        (
            await session.scalars(
                query.order_by(Transaction.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return TransactionPage(
        items=[
            TransactionView(
                id=item.id,
                resource_type=item.resource_type.value,
                amount=item.amount,
                balance_before=item.balance_before,
                balance_after=item.balance_after,
                reason=item.reason,
                reference_type=item.reference_type,
                reference_id=item.reference_id,
                created_at=item.created_at,
            )
            for item in rows
        ],
        next_cursor=(
            CursorCodec.encode(resource="transactions", last_id=rows[-1].id)
            if has_more and rows
            else None
        ),
    )


@router.post("/me/level/upgrade", response_model=LevelView)
async def upgrade_level(
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> LevelView:
        user = await level_service.upgrade(session, current.user.id)
        balances = await session.scalar(
            select(Resource).where(Resource.user_id == current.user.id)
        )
        next_cost = (
            None
            if user.level >= game_config.level_progression.max_level
            else level_service.upgrade_cost(user.level)
        )
        return LevelView(
            level=user.level,
            next_upgrade_cost=next_cost,
            maximum_level=game_config.level_progression.max_level,
            resources=resources(balances),
        )

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="level.upgrade",
        key=idempotency_key,
        payload={},
        action=action,
    )


@router.get("/users/search", response_model=list[UserSummary])
async def search_users(
    current: AuthenticatedUser,
    session: DatabaseSession,
    query: Annotated[str, Query(min_length=2, max_length=64)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> list[UserSummary]:
    normalized = query.strip().removeprefix("@").casefold()
    users = list(
        (
            await session.scalars(
                select(User)
                .where(
                    User.is_active.is_(True),
                    User.id != current.user.id,
                    func.lower(User.username).like(f"{normalized}%"),
                )
                .order_by(User.level.desc(), User.id)
                .limit(limit)
            )
        ).all()
    )
    return [user_summary(item) for item in users]


@router.get("/users/{user_id}/profile", response_model=PublicProfileView)
async def public_profile(
    user_id: int, current: AuthenticatedUser, session: DatabaseSession
) -> PublicProfileView:
    del current
    try:
        snapshot = await profile_service.snapshot(session, user_id)
    except ProfileNotFound as exc:
        raise APIError(404, "USER_NOT_FOUND", "کاربر پیدا نشد.") from exc
    if not snapshot.user.is_active:
        raise APIError(404, "USER_NOT_FOUND", "کاربر پیدا نشد.")
    return PublicProfileView(
        user=user_summary(snapshot.user),
        member_since=snapshot.user.created_at,
        teachers_count=snapshot.teachers_count,
        attacks_sent=snapshot.attacks_sent,
        successful_attacks=snapshot.successful_attacks,
        answers_count=snapshot.answers_count,
        correct_answers=snapshot.correct_answers,
    )
