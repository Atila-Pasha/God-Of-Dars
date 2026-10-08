import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.core.metrics import increment, timer
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class DatabaseSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        finish = timer("update")
        try:
            return await self._handle(handler, event, data)
        finally:
            finish()

    async def _handle(self, handler, event, data) -> Any:
        increment("updates")
        async with AsyncSessionLocal() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
            except Exception:
                increment("update_errors")
                await session.rollback()
                raise
            else:
                try:
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logger.exception("Database commit failed while processing update")
                    raise
            return result
