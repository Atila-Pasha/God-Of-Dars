from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from aiogram import Bot
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.errors import register_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.rate_limit import RateLimitMiddleware
from app.api.routes import (
    account,
    activities,
    auth,
    battles,
    bootstrap,
    profile,
    school,
    system,
)
from app.api.telegram_oidc import TelegramOIDCClient
from app.core.config import settings
from app.services.subscription_service import SubscriptionService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_api_production()
    timeout = httpx.Timeout(10.0, connect=5.0)
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        proxy=settings.API_OUTBOUND_PROXY,
        trust_env=False,
    ) as client:
        app.state.telegram_oidc = TelegramOIDCClient(client)
        app.state.telegram_bot = Bot(settings.BOT_TOKEN)
        app.state.subscription_service = SubscriptionService()
        app.state.redis = (
            Redis.from_url(settings.REDIS_URL, decode_responses=True)
            if settings.REDIS_URL
            else None
        )
        try:
            yield
        finally:
            if app.state.redis is not None:
                await app.state.redis.aclose()
            await app.state.telegram_bot.session.close()


def create_application() -> FastAPI:
    app = FastAPI(
        title="GodOfDars API",
        version="1.0.0",
        description="Public API for GodOfDars clients",
        lifespan=lifespan,
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        openapi_url=("/openapi.json" if settings.ENVIRONMENT != "production" else None),
        redoc_url=None,
    )
    register_error_handlers(app)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    origins = list(settings.api_allowed_origin_set)
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Idempotency-Key",
                "X-Login-Secret",
                "X-Request-ID",
            ],
            expose_headers=["X-Request-ID", "ETag", "Retry-After"],
        )
    app.include_router(system.health_router)
    app.include_router(system.meta_router, prefix="/api/v1")
    app.include_router(system.config_router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(bootstrap.router, prefix="/api/v1")
    app.include_router(profile.router, prefix="/api/v1")
    app.include_router(school.router, prefix="/api/v1")
    app.include_router(activities.router, prefix="/api/v1")
    app.include_router(battles.router, prefix="/api/v1")
    app.include_router(account.router, prefix="/api/v1")
    return app
