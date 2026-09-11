from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from app.api.main import app
from app.api.routes.account import _notification
from app.core.enums import NotificationStatus
from app.models.notification import Notification


def test_openapi_contains_public_v1_surface() -> None:
    paths = app.openapi()["paths"]
    required = {
        "/api/v1/auth/telegram/attempts",
        "/api/v1/auth/telegram/exchange",
        "/api/v1/auth/refresh",
        "/api/v1/bootstrap",
        "/api/v1/me/profile",
        "/api/v1/me/resources",
        "/api/v1/me/teachers",
        "/api/v1/me/castle",
        "/api/v1/me/mine",
        "/api/v1/me/study",
        "/api/v1/daily-question",
        "/api/v1/battles",
        "/api/v1/exchanges",
        "/api/v1/me/referral",
        "/api/v1/me/notifications",
    }
    assert required <= paths.keys()


def test_daily_question_response_never_exposes_correct_answer() -> None:
    schema = app.openapi()["components"]["schemas"]["DailyQuestionView"]
    assert "correct_answer" not in schema["properties"]


def test_notification_response_hides_telegram_delivery_coordinates() -> None:
    item = Notification(
        id=1,
        notification_type="TEST",
        recipient_user_id=1,
        idempotency_key="test-notification-contract",
        status=NotificationStatus.PENDING,
        payload={"chat_id": 123456789, "text": "hello", "level_confirmation": True},
        created_at=datetime.now(UTC),
    )
    view = _notification(item)
    assert view.payload == {"text": "hello", "level_confirmation": True}


@pytest.mark.asyncio
async def test_health_and_unauthenticated_error_envelope() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", trust_env=False
    ) as client:
        live = await client.get("/health/live")
        unauthorized = await client.get("/api/v1/me")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "AUTH_REQUIRED"
    assert unauthorized.json()["error"]["request_id"]
    assert unauthorized.headers["x-content-type-options"] == "nosniff"
