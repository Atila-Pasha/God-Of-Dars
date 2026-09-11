from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, cast

from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Limit:
    name: str
    requests: int
    seconds: int


class RateLimitMiddleware(BaseHTTPMiddleware):
    _script = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return current
"""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._local: dict[str, tuple[float, int]] = {}
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        policy = self._policy(request)
        if policy is None:
            return await call_next(request)
        identity = self._identity(request)
        window = int(time.time()) // policy.seconds
        key = f"godofdars:rate:{policy.name}:{identity}:{window}"
        allowed, remaining = await self._allow(request, key, policy)
        if not allowed:
            retry_after = policy.seconds - int(time.time()) % policy.seconds
            return JSONResponse(
                {
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "تعداد درخواست‌ها بیش از حد مجاز است.",
                        "details": {"retry_after_seconds": retry_after},
                        "request_id": getattr(request.state, "request_id", None),
                    }
                },
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(policy.requests)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        return response

    async def _allow(
        self, request: Request, key: str, policy: Limit
    ) -> tuple[bool, int]:
        redis: Redis | None = getattr(request.app.state, "redis", None)
        if redis is not None:
            try:
                result = await cast(
                    Awaitable[Any], redis.eval(self._script, 1, key, policy.seconds)
                )
                count = int(result)
                return count <= policy.requests, policy.requests - count
            except Exception:
                logger.warning("Redis rate limiter unavailable; using local fallback")
        async with self._lock:
            now = time.monotonic()
            if len(self._local) > 20_000:
                self._local = {
                    item_key: value
                    for item_key, value in self._local.items()
                    if value[0] > now
                }
            expires_at, count = self._local.get(key, (now + policy.seconds, 0))
            if expires_at <= now:
                expires_at, count = now + policy.seconds, 0
            count += 1
            self._local[key] = (expires_at, count)
            return count <= policy.requests, policy.requests - count

    @staticmethod
    def _identity(request: Request) -> str:
        authorization = request.headers.get("Authorization")
        if authorization:
            return hashlib.sha256(authorization.encode()).hexdigest()[:24]
        client = request.client.host if request.client else "unknown"
        return hashlib.sha256(client.encode()).hexdigest()[:24]

    @staticmethod
    def _policy(request: Request) -> Limit | None:
        path = request.url.path
        if path.startswith("/health/"):
            return None
        if path == "/api/v1/auth/telegram/attempts" and request.method == "POST":
            return Limit("login", 10, 60)
        if path.startswith("/api/v1/auth/"):
            return Limit("auth", 30, 60)
        if path == "/api/v1/me/subscription/verify" and request.method == "POST":
            return Limit("subscription-verify", 10, 60)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return Limit("mutation", 120, 60)
        return Limit("read", 300, 60)
