from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import APIError
from app.api.security import AccessTokenClaims, TokenService
from app.db.session import AsyncSessionLocal
from app.models.auth import AuthSession
from app.models.user import User

bearer = HTTPBearer(auto_error=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


@dataclass(frozen=True)
class CurrentUser:
    user: User
    auth_session: AuthSession
    claims: AccessTokenClaims


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise APIError(401, "AUTH_REQUIRED", "ورود به حساب لازم است.")
    claims = TokenService().decode_access_token(credentials.credentials)
    auth_session = await session.scalar(
        select(AuthSession).where(AuthSession.id == claims.session_id)
    )
    now = datetime.now(UTC)
    if (
        auth_session is None
        or auth_session.user_id != claims.user_id
        or auth_session.revoked_at is not None
        or _as_utc(auth_session.expires_at) <= now
    ):
        raise APIError(401, "SESSION_REVOKED", "نشست ورود معتبر نیست.")
    user = await session.scalar(
        select(User).where(User.id == claims.user_id, User.is_active.is_(True))
    )
    if user is None:
        raise APIError(403, "USER_INACTIVE", "حساب کاربری غیرفعال است.")
    return CurrentUser(user=user, auth_session=auth_session, claims=claims)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]
