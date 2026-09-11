from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import APIError
from app.api.schemas.auth import LoginAttemptCreate, TokenPair
from app.api.security import TokenService, random_token, secret_hash, secure_equal_hash
from app.api.telegram_oidc import TelegramOIDCClient
from app.core.config import settings
from app.models.auth import (
    AuthAuditEvent,
    AuthIdentity,
    AuthLoginAttempt,
    AuthRefreshToken,
    AuthSession,
)
from app.repositories.user import UserRepository
from app.services.daily_quest_service import DailyQuestService


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _valid_uuid(value: str, *, code: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise APIError(404, code, "درخواست ورود پیدا نشد.") from exc


@dataclass(frozen=True)
class CreatedAttempt:
    attempt: AuthLoginAttempt
    poll_secret: str
    authorization_url: str


class AuthService:
    def __init__(self) -> None:
        self.users = UserRepository()
        self.tokens = TokenService()

    async def create_attempt(
        self,
        session: AsyncSession,
        data: LoginAttemptCreate,
        oidc: TelegramOIDCClient,
    ) -> CreatedAttempt:
        oidc.ensure_configured()
        attempt_id = str(uuid4())
        poll_secret = random_token()
        state = random_token(36)
        nonce = random_token(32)
        code_verifier = random_token(64)
        attempt = AuthLoginAttempt(
            id=attempt_id,
            poll_secret_hash=secret_hash(poll_secret),
            state=state,
            nonce_hash=secret_hash(nonce),
            code_verifier=code_verifier,
            platform=data.platform,
            device_id=data.device_id,
            app_version=data.app_version,
            expires_at=datetime.now(UTC)
            + timedelta(minutes=settings.API_LOGIN_ATTEMPT_MINUTES),
        )
        session.add(attempt)
        await session.flush()
        return CreatedAttempt(
            attempt=attempt,
            poll_secret=poll_secret,
            authorization_url=(
                f"{settings.API_PUBLIC_BASE_URL.rstrip('/')}/api/v1/auth/telegram/authorize/{attempt_id}"
            ),
        )

    async def get_attempt(
        self,
        session: AsyncSession,
        *,
        attempt_id: str,
        poll_secret: str,
        for_update: bool = False,
    ) -> AuthLoginAttempt:
        attempt_id = _valid_uuid(attempt_id, code="LOGIN_ATTEMPT_NOT_FOUND")
        query = select(AuthLoginAttempt).where(AuthLoginAttempt.id == attempt_id)
        if for_update:
            query = query.with_for_update()
        attempt = await session.scalar(query)
        if attempt is None or not secure_equal_hash(
            poll_secret, attempt.poll_secret_hash
        ):
            raise APIError(404, "LOGIN_ATTEMPT_NOT_FOUND", "درخواست ورود پیدا نشد.")
        if attempt.status == "PENDING" and _utc(attempt.expires_at) <= datetime.now(
            UTC
        ):
            attempt.status = "EXPIRED"
            await session.flush()
        return attempt

    async def authorization_url(
        self, session: AsyncSession, attempt_id: str, oidc: TelegramOIDCClient
    ) -> str:
        attempt_id = _valid_uuid(attempt_id, code="LOGIN_ATTEMPT_NOT_FOUND")
        attempt = await session.scalar(
            select(AuthLoginAttempt)
            .where(AuthLoginAttempt.id == attempt_id)
            .with_for_update()
        )
        if attempt is None or attempt.status != "PENDING":
            raise APIError(409, "TELEGRAM_LOGIN_INVALID", "درخواست ورود معتبر نیست.")
        if _utc(attempt.expires_at) <= datetime.now(UTC):
            attempt.status = "EXPIRED"
            await session.flush()
            raise APIError(
                410, "TELEGRAM_LOGIN_EXPIRED", "زمان ورود به پایان رسیده است."
            )
        # The nonce itself is never persisted. It is derived from a server-side
        # random verifier, while only its hash is used for validation.
        nonce = attempt.code_verifier[:43]
        attempt.nonce_hash = secret_hash(nonce)
        await session.flush()
        return oidc.authorization_url(
            state=attempt.state,
            nonce=nonce,
            code_verifier=attempt.code_verifier,
        )

    async def complete_telegram_login(
        self,
        session: AsyncSession,
        *,
        state: str,
        code: str,
        oidc: TelegramOIDCClient,
    ) -> AuthLoginAttempt:
        attempt = await session.scalar(
            select(AuthLoginAttempt).where(AuthLoginAttempt.state == state)
        )
        if attempt is None:
            raise APIError(400, "TELEGRAM_LOGIN_INVALID", "درخواست ورود معتبر نیست.")
        if attempt.status == "APPROVED":
            return attempt
        if attempt.status != "PENDING" or _utc(attempt.expires_at) <= datetime.now(UTC):
            if attempt.status == "PENDING":
                attempt.status = "EXPIRED"
                await session.flush()
            raise APIError(
                410, "TELEGRAM_LOGIN_EXPIRED", "زمان ورود به پایان رسیده است."
            )
        code_verifier = attempt.code_verifier
        expected_nonce_hash = attempt.nonce_hash
        await session.commit()
        claims = await oidc.exchange_code(code=code, code_verifier=code_verifier)
        nonce = claims.get("nonce")
        if not isinstance(nonce, str) or not secure_equal_hash(
            nonce, expected_nonce_hash
        ):
            raise APIError(
                401, "TELEGRAM_TOKEN_INVALID", "nonce ورود تلگرام معتبر نیست."
            )
        attempt = await session.scalar(
            select(AuthLoginAttempt)
            .where(AuthLoginAttempt.state == state)
            .with_for_update()
        )
        if attempt is None:
            raise APIError(400, "TELEGRAM_LOGIN_INVALID", "درخواست ورود معتبر نیست.")
        if attempt.status == "APPROVED":
            return attempt
        if attempt.status != "PENDING" or _utc(attempt.expires_at) <= datetime.now(UTC):
            raise APIError(409, "TELEGRAM_LOGIN_INVALID", "درخواست ورود معتبر نیست.")
        try:
            telegram_user_id = int(claims["id"])
            subject = str(claims["sub"])
        except (KeyError, TypeError, ValueError) as exc:
            raise APIError(
                401,
                "TELEGRAM_PROFILE_MISSING",
                "شناسه کاربر در پاسخ تلگرام وجود ندارد.",
            ) from exc
        if telegram_user_id <= 0 or not subject:
            raise APIError(
                401, "TELEGRAM_PROFILE_MISSING", "شناسه کاربر تلگرام معتبر نیست."
            )
        # PostgreSQL cannot row-lock a user that does not exist yet.  A
        # transaction advisory lock serializes concurrent first logins for the
        # same Telegram account and prevents duplicate-user races.
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            await session.execute(select(func.pg_advisory_xact_lock(telegram_user_id)))
        identity = await session.scalar(
            select(AuthIdentity).where(
                AuthIdentity.provider == "telegram",
                AuthIdentity.subject == subject,
            )
        )
        identity_by_id = await session.scalar(
            select(AuthIdentity).where(
                AuthIdentity.provider == "telegram",
                AuthIdentity.provider_user_id == telegram_user_id,
            )
        )
        if (
            identity is not None
            and identity_by_id is not None
            and identity.user_id != identity_by_id.user_id
        ):
            raise APIError(
                409,
                "TELEGRAM_IDENTITY_CONFLICT",
                "هویت تلگرام با حساب دیگری تداخل دارد.",
            )
        user = await self.users.get_by_telegram_user_id(
            session, telegram_user_id, for_update=True
        )
        first_name, last_name = self._names(claims)
        username = self._optional_text(claims.get("preferred_username"), 255)
        if user is None:
            user = await self.users.create(
                session,
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
        else:
            if not user.is_active:
                raise APIError(403, "USER_INACTIVE", "حساب کاربری غیرفعال است.")
            await self.users.update_telegram_profile(
                session,
                user,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
        profile = {
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "picture": self._optional_text(claims.get("picture"), 2048),
        }
        linked_identity = identity or identity_by_id
        if linked_identity is None:
            linked_identity = AuthIdentity(
                user_id=user.id,
                provider="telegram",
                subject=subject,
                provider_user_id=telegram_user_id,
                profile=profile,
            )
            session.add(linked_identity)
        elif linked_identity.user_id != user.id:
            raise APIError(
                409,
                "TELEGRAM_IDENTITY_CONFLICT",
                "هویت تلگرام با حساب دیگری تداخل دارد.",
            )
        else:
            linked_identity.subject = subject
            linked_identity.provider_user_id = telegram_user_id
            linked_identity.profile = profile
        attempt.user_id = user.id
        attempt.status = "APPROVED"
        attempt.approved_at = datetime.now(UTC)
        session.add(
            AuthAuditEvent(
                user_id=user.id,
                event_type="TELEGRAM_LOGIN_APPROVED",
                event_metadata={"platform": attempt.platform},
            )
        )
        await session.flush()
        return attempt

    async def exchange_attempt(
        self,
        session: AsyncSession,
        *,
        attempt_id: str,
        poll_secret: str,
    ) -> TokenPair:
        attempt = await self.get_attempt(
            session,
            attempt_id=attempt_id,
            poll_secret=poll_secret,
            for_update=True,
        )
        if attempt.status == "EXCHANGED":
            raise APIError(
                409, "LOGIN_ATTEMPT_USED", "این درخواست ورود قبلاً مصرف شده است."
            )
        if attempt.status != "APPROVED" or attempt.user_id is None:
            raise APIError(
                409, "LOGIN_NOT_APPROVED", "ورود هنوز توسط تلگرام تأیید نشده است."
            )
        now = datetime.now(UTC)
        session_id = str(uuid4())
        family_id = str(uuid4())
        refresh_expires_at = now + timedelta(days=settings.API_REFRESH_TOKEN_DAYS)
        refresh_token, refresh_hash = self._new_refresh_token(session_id=session_id)
        auth_session = AuthSession(
            id=session_id,
            family_id=family_id,
            user_id=attempt.user_id,
            refresh_token_hash=refresh_hash,
            device_id=attempt.device_id,
            platform=attempt.platform,
            app_version=attempt.app_version,
            expires_at=refresh_expires_at,
        )
        session.add(auth_session)
        # Flush the parent explicitly before DailyQuestService can trigger a
        # nested flush.  The token uses a scalar FK instead of an ORM
        # relationship, so this also makes insertion order unambiguous.
        await session.flush()
        session.add(
            AuthRefreshToken(
                id=refresh_token.split(".", 1)[0],
                session_id=session_id,
                token_hash=refresh_hash,
                expires_at=refresh_expires_at,
            )
        )
        access_token, access_expires_at = self.tokens.create_access_token(
            user_id=attempt.user_id, session_id=session_id
        )
        attempt.status = "EXCHANGED"
        attempt.exchanged_at = now
        attempt.code_verifier = "consumed"
        attempt.state = f"used-{attempt.id}"
        session.add(
            AuthAuditEvent(
                user_id=attempt.user_id,
                session_id=session_id,
                event_type="SESSION_CREATED",
                event_metadata={"platform": attempt.platform},
            )
        )
        await DailyQuestService().record_event(
            session,
            user_id=attempt.user_id,
            event_type="DAILY_LOGIN",
            event_id=f"session:{session_id}",
        )
        await session.flush()
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
            session_id=session_id,
        )

    async def refresh(self, session: AsyncSession, raw_token: str) -> TokenPair:
        token_id = self._refresh_token_id(raw_token)
        token = await session.scalar(
            select(AuthRefreshToken)
            .where(AuthRefreshToken.id == token_id)
            .with_for_update()
        )
        if token is None or not secrets.compare_digest(
            secret_hash(raw_token), token.token_hash
        ):
            raise APIError(401, "REFRESH_TOKEN_INVALID", "توکن تمدید معتبر نیست.")
        auth_session = await session.scalar(
            select(AuthSession)
            .where(AuthSession.id == token.session_id)
            .with_for_update()
        )
        now = datetime.now(UTC)
        if auth_session is None or auth_session.revoked_at is not None:
            raise APIError(401, "SESSION_REVOKED", "نشست ورود معتبر نیست.")
        if token.used_at is not None or token.revoked_at is not None:
            auth_session.reuse_detected = True
            await session.execute(
                update(AuthSession)
                .where(AuthSession.family_id == auth_session.family_id)
                .values(revoked_at=now, reuse_detected=True)
            )
            session.add(
                AuthAuditEvent(
                    user_id=auth_session.user_id,
                    session_id=auth_session.id,
                    event_type="REFRESH_TOKEN_REUSE",
                    event_metadata={},
                )
            )
            await session.commit()
            raise APIError(
                401, "REFRESH_TOKEN_REUSED", "نشست ورود به دلیل استفاده مجدد لغو شد."
            )
        if _utc(token.expires_at) <= now or _utc(auth_session.expires_at) <= now:
            auth_session.revoked_at = now
            raise APIError(401, "REFRESH_TOKEN_EXPIRED", "زمان نشست ورود تمام شده است.")
        token.used_at = now
        new_refresh, new_hash = self._new_refresh_token(session_id=auth_session.id)
        new_token_id = new_refresh.split(".", 1)[0]
        session.add(
            AuthRefreshToken(
                id=new_token_id,
                session_id=auth_session.id,
                token_hash=new_hash,
                expires_at=auth_session.expires_at,
            )
        )
        auth_session.previous_refresh_token_hash = auth_session.refresh_token_hash
        auth_session.refresh_token_hash = new_hash
        auth_session.rotation_counter += 1
        auth_session.last_used_at = now
        access, access_expiry = self.tokens.create_access_token(
            user_id=auth_session.user_id, session_id=auth_session.id
        )
        await session.flush()
        return TokenPair(
            access_token=access,
            refresh_token=new_refresh,
            access_expires_at=access_expiry,
            refresh_expires_at=_utc(auth_session.expires_at),
            session_id=auth_session.id,
        )

    async def revoke_session(
        self, session: AsyncSession, *, session_id: str, user_id: int
    ) -> None:
        auth_session = await session.scalar(
            select(AuthSession)
            .where(AuthSession.id == session_id, AuthSession.user_id == user_id)
            .with_for_update()
        )
        if auth_session is not None and auth_session.revoked_at is None:
            auth_session.revoked_at = datetime.now(UTC)
            session.add(
                AuthAuditEvent(
                    user_id=user_id,
                    session_id=session_id,
                    event_type="SESSION_REVOKED",
                    event_metadata={},
                )
            )
            await session.flush()

    async def revoke_all(self, session: AsyncSession, *, user_id: int) -> None:
        now = datetime.now(UTC)
        await session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        session.add(
            AuthAuditEvent(
                user_id=user_id,
                event_type="ALL_SESSIONS_REVOKED",
                event_metadata={},
            )
        )

    @staticmethod
    def _new_refresh_token(*, session_id: str) -> tuple[str, str]:
        token_id = str(uuid4())
        raw = f"{token_id}.{random_token(48)}"
        return raw, secret_hash(raw)

    @staticmethod
    def _refresh_token_id(raw: str) -> str:
        try:
            token_id, secret = raw.split(".", 1)
            if len(secret) < 32:
                raise ValueError
            return str(UUID(token_id))
        except (ValueError, AttributeError) as exc:
            raise APIError(
                401, "REFRESH_TOKEN_INVALID", "توکن تمدید معتبر نیست."
            ) from exc

    @staticmethod
    def _optional_text(value: object, limit: int) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value[:limit] or None

    @classmethod
    def _names(cls, claims: dict) -> tuple[str, str | None]:
        first = cls._optional_text(claims.get("given_name"), 255)
        last = cls._optional_text(claims.get("family_name"), 255)
        if first:
            return first, last
        full = cls._optional_text(claims.get("name"), 510) or "کاربر تلگرام"
        parts = full.split(maxsplit=1)
        return parts[0][:255], (parts[1][:255] if len(parts) > 1 else last)
