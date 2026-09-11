from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from app.api.errors import APIError
from app.core.config import settings


def secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def random_token(bytes_count: int = 32) -> str:
    return secrets.token_urlsafe(bytes_count)


def secure_equal_hash(value: str, expected_hash: str) -> bool:
    return secrets.compare_digest(secret_hash(value), expected_hash)


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: int
    session_id: str
    token_id: str
    expires_at: datetime


class TokenService:
    algorithm = "HS256"

    def _secret(self) -> str:
        secret = settings.API_JWT_SECRET
        if not secret or len(secret.encode("utf-8")) < 32:
            raise APIError(
                503,
                "API_AUTH_NOT_CONFIGURED",
                "سامانه ورود هنوز پیکربندی نشده است.",
            )
        return secret

    def create_access_token(
        self, *, user_id: int, session_id: str
    ) -> tuple[str, datetime]:
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=settings.API_ACCESS_TOKEN_MINUTES)
        payload = {
            "iss": settings.API_JWT_ISSUER,
            "aud": settings.API_JWT_AUDIENCE,
            "sub": str(user_id),
            "sid": session_id,
            "jti": str(uuid4()),
            "typ": "access",
            "iat": now,
            "nbf": now,
            "exp": expires_at,
        }
        token = jwt.encode(payload, self._secret(), algorithm=self.algorithm)
        return token, expires_at

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret(),
                algorithms=[self.algorithm],
                audience=settings.API_JWT_AUDIENCE,
                issuer=settings.API_JWT_ISSUER,
                options={
                    "require": [
                        "exp",
                        "iat",
                        "nbf",
                        "iss",
                        "aud",
                        "sub",
                        "sid",
                        "jti",
                        "typ",
                    ]
                },
            )
            if payload.get("typ") != "access":
                raise InvalidTokenError("wrong token type")
            return AccessTokenClaims(
                user_id=int(payload["sub"]),
                session_id=str(payload["sid"]),
                token_id=str(payload["jti"]),
                expires_at=datetime.fromtimestamp(int(payload["exp"]), UTC),
            )
        except ExpiredSignatureError as exc:
            raise APIError(
                401, "TOKEN_EXPIRED", "زمان توکن ورود تمام شده است."
            ) from exc
        except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
            raise APIError(401, "TOKEN_INVALID", "توکن ورود معتبر نیست.") from exc
