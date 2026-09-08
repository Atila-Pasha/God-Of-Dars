import logging
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.core.metrics import increment, observe
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class DatabaseSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with AsyncSessionLocal() as session:
            data["session"] = session
            started = monotonic()
            try:
                result = await handler(event, data)
            except Exception:
                increment("updates.errors")
                await session.rollback()
                raise
            else:
                try:
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logger.exception("Database commit failed while processing update")
                    increment("database.commit_errors")
                    raise
            elapsed_ms = (monotonic() - started) * 1000
            observe("updates.duration_ms", elapsed_ms)
            increment("updates.completed")
            if elapsed_ms >= 1000:
                logger.warning(
                    "Slow update processing: %.1fms event=%s",
                    elapsed_ms,
                    type(event).__name__,
                )
            return result
