from __future__ import annotations

import asyncio
import secrets
import time
from base64 import urlsafe_b64encode
from hashlib import sha256
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import InvalidTokenError, PyJWK

from app.api.errors import APIError
from app.core.config import settings


def pkce_challenge(verifier: str) -> str:
    return (
        urlsafe_b64encode(sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


class TelegramOIDCClient:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self.http_client = http_client
        self._jwks: dict[str, Any] | None = None
        self._jwks_loaded_at = 0.0
        self._jwks_lock = asyncio.Lock()

    @staticmethod
    def ensure_configured() -> tuple[str, str]:
        if not settings.TELEGRAM_CLIENT_ID or not settings.TELEGRAM_CLIENT_SECRET:
            raise APIError(
                503,
                "TELEGRAM_LOGIN_NOT_CONFIGURED",
                "ورود با تلگرام هنوز پیکربندی نشده است.",
            )
        return settings.TELEGRAM_CLIENT_ID, settings.TELEGRAM_CLIENT_SECRET

    def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str:
        client_id, _ = self.ensure_configured()
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": settings.telegram_redirect_uri,
                "response_type": "code",
                "scope": settings.TELEGRAM_OIDC_SCOPES,
                "state": state,
                "nonce": nonce,
                "code_challenge": pkce_challenge(code_verifier),
                "code_challenge_method": "S256",
            }
        )
        return f"{settings.TELEGRAM_OIDC_AUTH_URL}?{query}"

    async def exchange_code(self, *, code: str, code_verifier: str) -> dict[str, Any]:
        client_id, client_secret = self.ensure_configured()
        try:
            response = await self.http_client.post(
                settings.TELEGRAM_OIDC_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.telegram_redirect_uri,
                    "client_id": client_id,
                    "code_verifier": code_verifier,
                },
                auth=httpx.BasicAuth(client_id, client_secret),
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise APIError(
                502,
                "TELEGRAM_LOGIN_UNAVAILABLE",
                "تأیید ورود تلگرام موقتاً ممکن نیست.",
            ) from exc
        id_token = payload.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise APIError(502, "TELEGRAM_TOKEN_INVALID", "پاسخ تلگرام معتبر نیست.")
        return await self.validate_id_token(id_token)

    async def _get_jwks(self, *, force: bool = False) -> dict[str, Any]:
        if (
            not force
            and self._jwks is not None
            and time.monotonic() - self._jwks_loaded_at < 3600
        ):
            return self._jwks
        async with self._jwks_lock:
            if (
                not force
                and self._jwks is not None
                and time.monotonic() - self._jwks_loaded_at < 3600
            ):
                return self._jwks
            try:
                response = await self.http_client.get(settings.TELEGRAM_OIDC_JWKS_URL)
                response.raise_for_status()
                jwks = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise APIError(
                    502,
                    "TELEGRAM_LOGIN_UNAVAILABLE",
                    "کلیدهای ورود تلگرام در دسترس نیستند.",
                ) from exc
            if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
                raise APIError(
                    502, "TELEGRAM_TOKEN_INVALID", "کلیدهای تلگرام معتبر نیستند."
                )
            self._jwks = jwks
            self._jwks_loaded_at = time.monotonic()
            return jwks

    async def _signing_key(self, token: str) -> Any:
        try:
            header = jwt.get_unverified_header(token)
        except InvalidTokenError as exc:
            raise APIError(
                401, "TELEGRAM_TOKEN_INVALID", "توکن تلگرام معتبر نیست."
            ) from exc
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise APIError(
                401, "TELEGRAM_TOKEN_INVALID", "الگوریتم توکن تلگرام معتبر نیست."
            )
        for force in (False, True):
            jwks = await self._get_jwks(force=force)
            for item in jwks["keys"]:
                if item.get("kid") == header["kid"]:
                    try:
                        return PyJWK.from_dict(item, algorithm="RS256").key
                    except (InvalidTokenError, ValueError) as exc:
                        raise APIError(
                            401,
                            "TELEGRAM_TOKEN_INVALID",
                            "کلید توکن تلگرام معتبر نیست.",
                        ) from exc
        raise APIError(
            401, "TELEGRAM_TOKEN_INVALID", "کلید امضای توکن تلگرام پیدا نشد."
        )

    async def validate_id_token(self, token: str) -> dict[str, Any]:
        client_id, _ = self.ensure_configured()
        key = await self._signing_key(token)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=settings.TELEGRAM_OIDC_ISSUER,
                options={
                    "verify_aud": False,
                    "require": ["iss", "sub", "iat", "exp", "aud", "nonce"],
                },
                leeway=30,
            )
        except InvalidTokenError as exc:
            raise APIError(
                401, "TELEGRAM_TOKEN_INVALID", "توکن تلگرام معتبر نیست."
            ) from exc
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if not any(
            secrets.compare_digest(str(value), str(client_id)) for value in audiences
        ):
            raise APIError(
                401, "TELEGRAM_TOKEN_INVALID", "مخاطب توکن تلگرام معتبر نیست."
            )
        return claims
