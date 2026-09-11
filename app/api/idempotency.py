from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import APIError
from app.core.config import settings
from app.models.auth import ApiIdempotencyRequest


def _request_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_key(value: str | None) -> str:
    if value is None:
        raise APIError(
            400,
            "IDEMPOTENCY_KEY_REQUIRED",
            "برای این عملیات Idempotency-Key لازم است.",
        )
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise APIError(
            400,
            "IDEMPOTENCY_KEY_INVALID",
            "Idempotency-Key باید UUID معتبر باشد.",
        ) from exc


async def run_idempotent(
    session: AsyncSession,
    *,
    user_id: int,
    operation: str,
    key: str | None,
    payload: Any,
    action: Callable[[], Awaitable[dict[str, Any]]],
    response_status: int = 200,
) -> tuple[dict[str, Any], int, bool]:
    normalized_key = validate_key(key)
    digest = _request_hash(payload)
    query = select(ApiIdempotencyRequest).where(
        ApiIdempotencyRequest.user_id == user_id,
        ApiIdempotencyRequest.operation == operation,
        ApiIdempotencyRequest.idempotency_key == normalized_key,
    )
    record: ApiIdempotencyRequest | None = None
    existing = await session.scalar(query.with_for_update())
    if existing is None:
        record = ApiIdempotencyRequest(
            user_id=user_id,
            operation=operation,
            idempotency_key=normalized_key,
            request_hash=digest,
            expires_at=datetime.now(UTC)
            + timedelta(hours=settings.API_IDEMPOTENCY_HOURS),
        )
        try:
            async with session.begin_nested():
                session.add(record)
                await session.flush()
            existing = record
        except IntegrityError:
            existing = await session.scalar(query.with_for_update())
    if existing is None:
        raise APIError(
            409, "IDEMPOTENCY_CONFLICT", "عملیات هم‌زمان دیگری در حال اجراست."
        )
    if existing.request_hash != digest:
        raise APIError(
            409,
            "IDEMPOTENCY_KEY_REUSED",
            "این کلید قبلاً برای درخواست دیگری استفاده شده است.",
        )
    if existing.status == "COMPLETED":
        if existing.response_body is None or existing.response_status is None:
            raise APIError(
                500, "IDEMPOTENCY_RECORD_INVALID", "رکورد عملیات معتبر نیست."
            )
        return existing.response_body, existing.response_status, True
    if record is None or existing is not record:
        raise APIError(
            409,
            "IDEMPOTENCY_IN_PROGRESS",
            "این عملیات در حال پردازش است.",
            headers={"Retry-After": "1"},
        )
    result = await action()
    existing.status = "COMPLETED"
    existing.response_status = response_status
    existing.response_body = result
    await session.flush()
    return result, response_status, False
