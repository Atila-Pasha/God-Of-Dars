from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.idempotency import run_idempotent


async def idempotent_response(
    session: AsyncSession,
    *,
    user_id: int,
    operation: str,
    key: str | None,
    payload: Any,
    action: Callable[[], Awaitable[Any]],
    status_code: int = 200,
) -> JSONResponse:
    async def encoded_action() -> dict[str, Any]:
        encoded = jsonable_encoder(await action())
        if not isinstance(encoded, dict):
            raise TypeError("idempotent actions must return an object")
        return encoded

    result, result_status, replayed = await run_idempotent(
        session,
        user_id=user_id,
        operation=operation,
        key=key,
        payload=payload,
        action=encoded_action,
        response_status=status_code,
    )
    return JSONResponse(
        result,
        status_code=result_status,
        headers={"Idempotency-Replayed": "true" if replayed else "false"},
    )
