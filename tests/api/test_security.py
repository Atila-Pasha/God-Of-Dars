from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.api.cursors import CursorCodec
from app.api.errors import APIError
from app.api.idempotency import validate_key
from app.api.security import TokenService
from app.api.telegram_oidc import TelegramOIDCClient, pkce_challenge
from app.core.config import settings


def test_access_token_round_trip_and_wrong_audience(monkeypatch) -> None:
    monkeypatch.setattr(settings, "API_JWT_SECRET", "x" * 64)
    monkeypatch.setattr(settings, "API_JWT_AUDIENCE", "godofdars-test")
    token, expires_at = TokenService().create_access_token(user_id=42, session_id="s1")
    claims = TokenService().decode_access_token(token)
    assert claims.user_id == 42
    assert claims.session_id == "s1"
    assert claims.expires_at == expires_at.replace(microsecond=0)

    monkeypatch.setattr(settings, "API_JWT_AUDIENCE", "another-client")
    with pytest.raises(APIError, match="توکن ورود معتبر نیست"):
        TokenService().decode_access_token(token)


def test_expired_access_token_has_stable_error_code(monkeypatch) -> None:
    monkeypatch.setattr(settings, "API_JWT_SECRET", "z" * 64)
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": settings.API_JWT_ISSUER,
            "aud": settings.API_JWT_AUDIENCE,
            "sub": "42",
            "sid": "session",
            "jti": "token",
            "typ": "access",
            "iat": now - timedelta(minutes=2),
            "nbf": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
        },
        settings.API_JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(APIError) as error:
        TokenService().decode_access_token(token)
    assert error.value.code == "TOKEN_EXPIRED"


def test_cursor_is_scoped_and_tamper_evident(monkeypatch) -> None:
    monkeypatch.setattr(settings, "API_JWT_SECRET", "y" * 64)
    value = CursorCodec.encode(resource="transactions", last_id=123)
    assert CursorCodec.decode(value, resource="transactions") == 123
    with pytest.raises(APIError):
        CursorCodec.decode(value, resource="notifications")
    with pytest.raises(APIError):
        CursorCodec.decode(value[:-1] + "A", resource="transactions")


def test_idempotency_key_requires_uuid() -> None:
    assert validate_key("0f5df181-c88b-4bc8-8243-adde4bc66f91") == (
        "0f5df181-c88b-4bc8-8243-adde4bc66f91"
    )
    with pytest.raises(APIError):
        validate_key("not-a-uuid")


def test_pkce_uses_rfc7636_s256_vector() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert pkce_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


@pytest.mark.asyncio
async def test_telegram_id_token_signature_claims_and_audience(monkeypatch) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_CLIENT_ID", "123456789")
    monkeypatch.setattr(settings, "TELEGRAM_CLIENT_SECRET", "secret")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk["kid"] = "test-key"
    now = datetime.now(UTC)

    async with httpx.AsyncClient(trust_env=False) as http_client:
        client = TelegramOIDCClient(http_client)

        async def fake_jwks(*, force: bool = False):
            del force
            return {"keys": [jwk]}

        monkeypatch.setattr(client, "_get_jwks", fake_jwks)
        claims = {
            "iss": settings.TELEGRAM_OIDC_ISSUER,
            "aud": "123456789",
            "sub": "telegram-subject",
            "id": 987654321,
            "nonce": "nonce",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        }
        token = jwt.encode(
            claims,
            private_key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )
        validated = await client.validate_id_token(token)
        assert validated["id"] == 987654321

        claims["aud"] = "wrong-client"
        wrong_audience = jwt.encode(
            claims,
            private_key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )
        with pytest.raises(APIError, match="مخاطب توکن"):
            await client.validate_id_token(wrong_audience)
