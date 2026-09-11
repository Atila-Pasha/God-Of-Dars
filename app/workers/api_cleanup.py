from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.auth import (
    ApiIdempotencyRequest,
    AuthLoginAttempt,
    AuthRefreshToken,
    AuthSession,
)

logger = logging.getLogger(__name__)


async def cleanup_api_state(*, now: datetime | None = None) -> None:
    """Bound transient API tables while retaining a short incident window."""
    now = now or datetime.now(UTC)
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(
            delete(ApiIdempotencyRequest).where(ApiIdempotencyRequest.expires_at < now)
        )
        await session.execute(
            delete(AuthLoginAttempt).where(
                AuthLoginAttempt.expires_at < now - timedelta(days=1)
            )
        )
        await session.execute(
            delete(AuthRefreshToken).where(
                AuthRefreshToken.expires_at < now - timedelta(days=7)
            )
        )
        await session.execute(
            delete(AuthSession).where(
                AuthSession.expires_at < now - timedelta(days=30),
                or_(
                    AuthSession.revoked_at.is_(None),
                    AuthSession.revoked_at < now - timedelta(days=30),
                ),
            )
        )


async def run_api_cleanup_worker() -> None:
    while True:
        try:
            await cleanup_api_state()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("API cleanup failed; retrying later")
        await asyncio.sleep(settings.API_CLEANUP_INTERVAL_SECONDS)
