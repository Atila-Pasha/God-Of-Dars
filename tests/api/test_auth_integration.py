from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.api.auth_service import AuthService
from app.api.errors import APIError
from app.api.schemas.auth import LoginAttemptCreate
from app.api.security import TokenService
from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine
from app.models.auth import AuthIdentity, AuthSession
from app.models.user import User

pytestmark = pytest.mark.skipif(
    not settings.DATABASE_URL.startswith("postgresql"),
    reason="requires PostgreSQL",
)


class FakeTelegramOIDC:
    def __init__(self, telegram_user_id: int) -> None:
        self.telegram_user_id = telegram_user_id
        self.nonce = ""

    @staticmethod
    def ensure_configured() -> tuple[str, str]:
        return "client", "secret"

    def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str:
        assert state and code_verifier
        self.nonce = nonce
        return "https://oauth.telegram.org/auth?test=1"

    async def exchange_code(self, *, code: str, code_verifier: str) -> dict:
        assert code and code_verifier and self.nonce
        return {
            "id": self.telegram_user_id,
            "sub": f"telegram:{self.telegram_user_id}",
            "nonce": self.nonce,
            "given_name": "API",
            "family_name": "User",
            "preferred_username": f"api_{self.telegram_user_id}",
        }


@pytest.fixture(autouse=True)
async def isolate_postgres_connections():
    await engine.dispose()
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_telegram_login_exchange_rotation_and_reuse_revocation(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "API_JWT_SECRET", "integration-test-secret-" * 3)
    telegram_user_id = int(uuid4().int % 2_000_000_000) + 3_000_000_000
    oidc = FakeTelegramOIDC(telegram_user_id)
    service = AuthService()
    user_id: int | None = None

    try:
        async with AsyncSessionLocal() as session:
            created = await service.create_attempt(
                session,
                LoginAttemptCreate(
                    device_id="integration-device-0001",
                    platform="linux",
                    app_version="1.0.0",
                ),
                oidc,  # type: ignore[arg-type]
            )
            attempt_id = created.attempt.id
            poll_secret = created.poll_secret
            await session.commit()

        async with AsyncSessionLocal() as session:
            assert await service.authorization_url(
                session,
                attempt_id,
                oidc,  # type: ignore[arg-type]
            )
            await session.commit()

        async with AsyncSessionLocal() as session:
            attempt = await service.complete_telegram_login(
                session,
                state=created.attempt.state,
                code="authorization-code",
                oidc=oidc,  # type: ignore[arg-type]
            )
            user_id = attempt.user_id
            assert user_id is not None
            await session.commit()

        async with AsyncSessionLocal() as session:
            pair = await service.exchange_attempt(
                session, attempt_id=attempt_id, poll_secret=poll_secret
            )
            await session.commit()
        claims = TokenService().decode_access_token(pair.access_token)
        assert claims.user_id == user_id
        assert claims.session_id == pair.session_id

        async with AsyncSessionLocal() as session:
            rotated = await service.refresh(session, pair.refresh_token)
            await session.commit()
        assert rotated.refresh_token != pair.refresh_token

        async with AsyncSessionLocal() as session:
            with pytest.raises(APIError) as reused:
                await service.refresh(session, pair.refresh_token)
            assert reused.value.code == "REFRESH_TOKEN_REUSED"

        async with AsyncSessionLocal() as session:
            auth_session = await session.get(AuthSession, pair.session_id)
            assert auth_session is not None
            assert auth_session.revoked_at is not None
            assert auth_session.reuse_detected is True
            identity = await session.scalar(
                select(AuthIdentity).where(AuthIdentity.user_id == user_id)
            )
            assert identity is not None
            assert identity.provider_user_id == telegram_user_id
    finally:
        if user_id is not None:
            async with AsyncSessionLocal() as session, session.begin():
                await session.execute(delete(User).where(User.id == user_id))
