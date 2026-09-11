# GodOfDars API

The HTTP API is part of the same Python package as the Telegram bot so both
clients reuse the existing transaction-safe domain services. It is deployed as
an independent process and never shares a client-side secret with Flet.

## Run locally

```bash
alembic upgrade head
python -m app.api
```

In development, OpenAPI is available at `http://127.0.0.1:8000/docs`.

## Telegram login flow

1. The Flet client creates `POST /api/v1/auth/telegram/attempts`.
2. It opens the returned `authorization_url` in the system browser.
3. Telegram redirects to the server callback. The server validates OIDC
   signature, issuer, audience, expiry, nonce, state, and PKCE.
4. Flet polls the attempt with `X-Login-Secret`, then exchanges the approved
   attempt for a short-lived access token and a rotating refresh token.

The Telegram client secret, JWT signing secret, PKCE verifier, and stored token
hashes remain server-side. Refresh-token reuse revokes the whole token family.

## Production requirements

- HTTPS public base URL and callback registered with BotFather
- `API_JWT_SECRET` containing at least 32 random bytes
- Telegram OIDC client ID and client secret
- PostgreSQL migration at the current Alembic head
- Redis for cross-process rate limiting (the local limiter is only a fallback)
- trusted proxy/header configuration so login rate limits see the real client IP

All state-changing economy endpoints require a UUID in `Idempotency-Key`.
