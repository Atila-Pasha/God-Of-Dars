"""Drain aiogram's admitted updates before closing HTTP and database pools."""

import asyncio
import logging

from aiogram import Dispatcher

logger = logging.getLogger(__name__)


async def drain_updates(dispatcher: Dispatcher, timeout: float = 40) -> None:
    # aiogram 3 tracks admitted polling tasks here but start_polling does not
    # await them on shutdown. Snapshot only after polling has stopped.
    tasks = set(dispatcher._handle_update_tasks)
    if not tasks:
        return
    _, pending = await asyncio.wait(tasks, timeout=timeout)
    if pending:
        logger.warning("Shutdown timed out with %s updates; rolling back", len(pending))
        for task in pending:
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
