from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update

from app.api.cursors import CursorCodec
from app.api.dependencies import AuthenticatedUser, DatabaseSession
from app.api.errors import APIError
from app.api.presenters import resources
from app.api.responses import idempotent_response
from app.api.schemas.domain import (
    ChanceCardView,
    ChanceClaimRequest,
    ExchangeOptionView,
    ExchangeRequest,
    ExchangeView,
    NotificationPage,
    NotificationReadAllRequest,
    NotificationView,
    ReferralApplyRequest,
    ReferralApplyView,
    ReferralView,
    ReferredUserView,
    SubscriptionChannelView,
    SubscriptionView,
)
from app.core.config import settings
from app.core.enums import ResourceType
from app.models.chance_card import ChanceCard
from app.models.notification import Notification
from app.models.resource import Resource
from app.repositories.bot_settings import BotSettingsRepository
from app.services.buffet_service import BuffetService
from app.services.chance_service import ChanceService
from app.services.referral_service import ReferralService
from app.services.subscription_service import MembershipCheckError, SubscriptionService

router = APIRouter(tags=["account"])
buffet = BuffetService()
referrals = ReferralService()
chance = ChanceService()
bot_settings = BotSettingsRepository()


@router.get("/exchanges/options", response_model=list[ExchangeOptionView])
async def exchange_options(current: AuthenticatedUser) -> list[ExchangeOptionView]:
    del current
    return [
        ExchangeOptionView(
            source=item.source.value,
            target=item.target.value,
            source_amount=item.source_amount,
            target_amount=item.target_amount,
        )
        for item in buffet.options()
    ]


@router.post("/exchanges", response_model=ExchangeView)
async def exchange_resources(
    body: ExchangeRequest,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    try:
        source = ResourceType(body.source.upper())
        target = ResourceType(body.target.upper())
    except ValueError as exc:
        raise APIError(400, "INVALID_RESOURCE_TYPE", "نوع منبع معتبر نیست.") from exc

    async def action() -> ExchangeView:
        result = await buffet.exchange(
            session,
            current.user.id,
            source=source,
            target=target,
            source_amount=body.source_amount,
        )
        balance = await session.scalar(
            select(Resource).where(Resource.user_id == current.user.id)
        )
        return ExchangeView(
            option=ExchangeOptionView(
                source=result.conversion.source.value,
                target=result.conversion.target.value,
                source_amount=result.conversion.source_amount,
                target_amount=result.conversion.target_amount,
            ),
            packages=result.packages,
            balances=resources(balance),
        )

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="buffet.exchange",
        key=idempotency_key,
        payload=body.model_dump(mode="json"),
        action=action,
    )


@router.get("/me/referral", response_model=ReferralView)
async def my_referral(
    current: AuthenticatedUser, session: DatabaseSession
) -> ReferralView:
    code = referrals.payload_for(current.user.id)
    deep_link = (
        f"https://t.me/{settings.BOT_USERNAME.lstrip('@')}?start={code}"
        if settings.BOT_USERNAME
        else None
    )
    return ReferralView(
        code=code,
        deep_link=deep_link,
        count=await referrals.count(session, current.user.id),
        referrer_id=current.user.referrer_id,
    )


@router.post("/me/referral/apply", response_model=ReferralApplyView)
async def apply_referral(
    body: ReferralApplyRequest,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    referrer_id = referrals.parse_payload(body.code)
    if referrer_id is None:
        raise APIError(400, "INVALID_REFERRAL_CODE", "کد دعوت معتبر نیست.")

    async def action() -> ReferralApplyView:
        result = await referrals.apply(
            session,
            referred_user_id=current.user.id,
            referrer_id=referrer_id,
        )
        return ReferralApplyView(
            applied=result.applied,
            referrer_id=result.referrer.id if result.referrer else None,
        )

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="referral.apply",
        key=idempotency_key,
        payload={"referrer_id": referrer_id},
        action=action,
    )


@router.get("/me/referrals", response_model=list[ReferredUserView])
async def referred_users(
    current: AuthenticatedUser, session: DatabaseSession
) -> list[ReferredUserView]:
    return [
        ReferredUserView(
            id=item.id,
            username=item.username,
            name=" ".join(part for part in (item.first_name, item.last_name) if part),
            level=item.level,
            joined_at=item.created_at,
        )
        for item in await referrals.list_referrals(session, current.user.id)
    ]


@router.get("/me/chance-cards", response_model=list[ChanceCardView])
async def chance_cards(
    current: AuthenticatedUser, session: DatabaseSession
) -> list[ChanceCardView]:
    items = list(
        (
            await session.scalars(
                select(ChanceCard)
                .where(ChanceCard.user_id == current.user.id)
                .order_by(ChanceCard.id.desc())
                .limit(100)
            )
        ).all()
    )
    return [
        ChanceCardView(
            id=item.id,
            resource_type=item.resource_type.value,
            amount=item.amount,
            claimed=item.is_claimed,
            created_at=item.created_at,
        )
        for item in items
    ]


@router.post("/me/chance-cards/{card_id}/claim", response_model=ChanceCardView)
async def claim_chance_card(
    card_id: int,
    body: ChanceClaimRequest,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> ChanceCardView:
        item = await chance.claim_card(session, card_id, current.user.id, body.answer)
        return ChanceCardView(
            id=item.id,
            resource_type=item.resource_type.value,
            amount=item.amount,
            claimed=item.is_claimed,
            created_at=item.created_at,
        )

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="chance-card.claim",
        key=idempotency_key,
        payload={"card_id": card_id, "answer": body.answer},
        action=action,
    )


@router.get("/me/notifications", response_model=NotificationPage)
async def notifications(
    current: AuthenticatedUser,
    session: DatabaseSession,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> NotificationPage:
    before_id = CursorCodec.decode(cursor, resource="notifications")
    query = select(Notification).where(
        Notification.recipient_user_id == current.user.id
    )
    if before_id is not None:
        query = query.where(Notification.id < before_id)
    rows = list(
        (
            await session.scalars(
                query.order_by(Notification.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return NotificationPage(
        items=[_notification(item) for item in rows],
        next_cursor=(
            CursorCodec.encode(resource="notifications", last_id=rows[-1].id)
            if has_more and rows
            else None
        ),
    )


@router.post(
    "/me/notifications/{notification_id}/read", response_model=NotificationView
)
async def read_notification(
    notification_id: int,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> NotificationView:
        item = await session.scalar(
            select(Notification)
            .where(
                Notification.id == notification_id,
                Notification.recipient_user_id == current.user.id,
            )
            .with_for_update()
        )
        if item is None:
            raise APIError(404, "NOTIFICATION_NOT_FOUND", "اعلان پیدا نشد.")
        item.read_at = item.read_at or datetime.now(UTC)
        await session.flush()
        return _notification(item)

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="notification.read",
        key=idempotency_key,
        payload={"notification_id": notification_id},
        action=action,
    )


@router.post("/me/notifications/read-all")
async def read_all_notifications(
    body: NotificationReadAllRequest,
    current: AuthenticatedUser,
    session: DatabaseSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def action() -> dict:
        statement = update(Notification).where(
            Notification.recipient_user_id == current.user.id,
            Notification.read_at.is_(None),
        )
        if body.through_id is not None:
            statement = statement.where(Notification.id <= body.through_id)
        result = await session.execute(statement.values(read_at=datetime.now(UTC)))
        return {"updated": int(getattr(result, "rowcount", 0) or 0)}

    return await idempotent_response(
        session,
        user_id=current.user.id,
        operation="notification.read-all",
        key=idempotency_key,
        payload=body.model_dump(mode="json"),
        action=action,
    )


@router.get("/me/subscription", response_model=SubscriptionView)
async def subscription_status(
    request: Request,
    current: AuthenticatedUser,
    session: DatabaseSession,
) -> SubscriptionView:
    return await _subscription_status(request, current, session, force=False)


@router.post("/me/subscription/verify", response_model=SubscriptionView)
async def verify_subscription(
    request: Request,
    current: AuthenticatedUser,
    session: DatabaseSession,
) -> SubscriptionView:
    return await _subscription_status(request, current, session, force=True)


async def _subscription_status(
    request: Request,
    current: AuthenticatedUser,
    session: DatabaseSession,
    *,
    force: bool,
) -> SubscriptionView:
    channels = await bot_settings.list_channels(session)
    labels = [
        str(item.telegram_id) if item.telegram_id else f"@{item.username}"
        for item in channels
    ]
    await session.commit()
    subscription: SubscriptionService = request.app.state.subscription_service
    subscription.set_channels(labels)
    try:
        member = await subscription.is_member(
            request.app.state.telegram_bot,
            current.user.telegram_user_id,
            force_refresh=force,
        )
        available = True
    except MembershipCheckError:
        member = None
        available = False
    return SubscriptionView(
        member=member,
        provider_available=available,
        checked_at=datetime.now(UTC),
        channels=[
            SubscriptionChannelView(
                id=item.id,
                title=(f"@{item.username}" if item.username else "کانال خصوصی"),
                url=(f"https://t.me/{item.username}" if item.username else None),
            )
            for item in channels
        ],
    )


def _notification(item: Notification) -> NotificationView:
    # The outbox also contains Telegram delivery coordinates such as chat_id.
    # They are transport details and must not cross the public API boundary.
    public_payload = {
        key: value
        for key, value in item.payload.items()
        if key in {"text", "level_confirmation"}
    }
    return NotificationView(
        id=item.id,
        type=item.notification_type,
        payload=public_payload,
        delivery_status=item.status.value,
        created_at=item.created_at,
        sent_at=item.sent_at,
        read_at=item.read_at,
    )
