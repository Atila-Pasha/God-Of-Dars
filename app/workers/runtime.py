from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from app.core.config import settings
from app.workers.attack_resolver import resolve_due_attacks

logger = logging.getLogger(__name__)


async def _attack_worker(bot: Bot, worker_id: int) -> None:
    while True:
        try:
            await resolve_due_attacks(bot, batch_size=settings.WORKER_BATCH_SIZE)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Attack worker %s failed; retrying", worker_id)
        await asyncio.sleep(settings.WORKER_POLL_INTERVAL)


async def run_workers(bot: Bot) -> None:
    """Run database-backed jobs concurrently without duplicating work."""
    async with asyncio.TaskGroup() as task_group:
        for worker_id in range(settings.WORKER_COUNT):
            task_group.create_task(_attack_worker(bot, worker_id))
