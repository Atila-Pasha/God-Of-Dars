from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Header, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.api.auth_service import AuthService
from app.api.dependencies import AuthenticatedUser, DatabaseSession
from app.api.errors import APIError
from app.api.schemas.auth import (
    AuthSessionView,
    LoginAttemptCreate,
    LoginAttemptCreated,
    LoginAttemptStatus,
    LoginExchangeRequest,
    RefreshRequest,
    TokenPair,
)
from app.api.telegram_oidc import TelegramOIDCClient
from app.models.auth import AuthLoginAttempt, AuthSession

router = APIRouter(prefix="/auth", tags=["authentication"])
service = AuthService()


def _oidc(request: Request) -> TelegramOIDCClient:
    return request.app.state.telegram_oidc


@router.post(
    "/telegram/attempts",
    response_model=LoginAttemptCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_telegram_attempt(
    body: LoginAttemptCreate, session: DatabaseSession, request: Request
) -> LoginAttemptCreated:
    created = await service.create_attempt(session, body, _oidc(request))
    return LoginAttemptCreated(
        attempt_id=created.attempt.id,
        poll_secret=created.poll_secret,
        authorization_url=created.authorization_url,
        expires_at=created.attempt.expires_at,
    )


@router.get("/telegram/attempts/{attempt_id}", response_model=LoginAttemptStatus)
async def telegram_attempt_status(
    attempt_id: str,
    session: DatabaseSession,
    poll_secret: Annotated[str, Header(alias="X-Login-Secret", min_length=32)],
) -> LoginAttemptStatus:
    attempt = await service.get_attempt(
        session, attempt_id=attempt_id, poll_secret=poll_secret
    )
    return LoginAttemptStatus(
        attempt_id=attempt.id,
        status=cast(
            Literal["PENDING", "APPROVED", "EXPIRED", "FAILED", "EXCHANGED"],
            attempt.status,
        ),
        expires_at=attempt.expires_at,
        error_code=attempt.error_code,
    )


@router.get("/telegram/authorize/{attempt_id}", include_in_schema=False)
async def authorize_telegram(
    attempt_id: str, session: DatabaseSession, request: Request
) -> RedirectResponse:
    url = await service.authorization_url(session, attempt_id, _oidc(request))
    return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/telegram/callback", response_class=HTMLResponse, include_in_schema=False)
async def telegram_callback(
    request: Request,
    session: DatabaseSession,
    state_value: Annotated[
        str | None, Query(alias="state", min_length=32, max_length=128)
    ] = None,
    code: Annotated[str | None, Query(min_length=1, max_length=4096)] = None,
    provider_error: Annotated[
        str | None, Query(alias="error", min_length=1, max_length=128)
    ] = None,
) -> HTMLResponse:
    if not state_value:
        return _callback_page(False)
    if provider_error or not code:
        attempt = await session.scalar(
            select(AuthLoginAttempt)
            .where(AuthLoginAttempt.state == state_value)
            .with_for_update()
        )
        if attempt is not None and attempt.status == "PENDING":
            attempt.status = "FAILED"
            attempt.error_code = "TELEGRAM_AUTH_DENIED"
        return _callback_page(False)
    try:
        await service.complete_telegram_login(
            session,
            state=state_value,
            code=code,
            oidc=_oidc(request),
        )
    except APIError:
        # This endpoint renders a browser-friendly page instead of letting the
        # global exception handler build JSON.  Roll back explicitly so a
        # failed callback can never commit partial identity/profile changes.
        await session.rollback()
        return _callback_page(False)
    return _callback_page(True)


@router.post("/telegram/exchange", response_model=TokenPair)
async def exchange_telegram_attempt(
    body: LoginExchangeRequest, session: DatabaseSession
) -> TokenPair:
    return await service.exchange_attempt(
        session,
        attempt_id=body.attempt_id,
        poll_secret=body.poll_secret,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh_tokens(body: RefreshRequest, session: DatabaseSession) -> TokenPair:
    return await service.refresh(session, body.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current: AuthenticatedUser, session: DatabaseSession) -> Response:
    await service.revoke_session(
        session, session_id=current.auth_session.id, user_id=current.user.id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(current: AuthenticatedUser, session: DatabaseSession) -> Response:
    await service.revoke_all(session, user_id=current.user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", response_model=list[AuthSessionView])
async def list_sessions(
    current: AuthenticatedUser, session: DatabaseSession
) -> list[AuthSessionView]:
    sessions = list(
        (
            await session.scalars(
                select(AuthSession)
                .where(
                    AuthSession.user_id == current.user.id,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > datetime.now(UTC),
                )
                .order_by(AuthSession.last_used_at.desc(), AuthSession.id)
            )
        ).all()
    )
    return [
        AuthSessionView.model_validate(item).model_copy(
            update={"current": item.id == current.auth_session.id}
        )
        for item in sessions
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: str, current: AuthenticatedUser, session: DatabaseSession
) -> Response:
    await service.revoke_session(
        session, session_id=session_id, user_id=current.user.id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _callback_page(success: bool) -> HTMLResponse:
    title = "ورود موفق" if success else "ورود ناموفق"
    message = (
        "حساب تلگرام تأیید شد. می‌توانید به برنامه GodOfDars برگردید."
        if success
        else "ورود تأیید نشد. به برنامه برگردید و دوباره تلاش کنید."
    )
    color = "#16794b" if success else "#a12b2b"
    html = f"""<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title></head>
<body style="font-family:sans-serif;background:#f7f5ee;margin:0;display:grid;place-items:center;min-height:100vh">
<main style="max-width:32rem;padding:2rem;text-align:center;background:white;border-radius:1rem">
<h1 style="color:{color}">{title}</h1><p>{message}</p></main></body></html>"""
    return HTMLResponse(
        html,
        status_code=200 if success else 400,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
        },
    )
