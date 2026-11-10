from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from app.core.config import settings
from app.services.rank_service import settle_expired_seasons
from app.workers.attack_resolver import resolve_due_archer_shots, resolve_due_attacks
from app.workers.car_game_tick import run_car_game_ticks
from app.workers.chess_timeout import run_chess_timeouts
from app.workers.game_message_cleanup import run_game_message_cleanup_worker
from app.workers.notification_worker import run_notification_worker
from app.workers.tic_tac_toe_timeout import run_tic_tac_toe_timeouts

logger = logging.getLogger(__name__)


async def _attack_worker(bot: Bot, worker_id: int) -> None:
    while True:
        processed = 0
        try:
            await resolve_due_archer_shots(batch_size=settings.WORKER_BATCH_SIZE)
            processed = await resolve_due_attacks(
                bot, batch_size=settings.WORKER_BATCH_SIZE
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Attack worker %s failed; retrying", worker_id)
        await asyncio.sleep(
            0
            if processed >= settings.WORKER_BATCH_SIZE
            else settings.WORKER_POLL_INTERVAL
        )


async def _rank_worker() -> None:
    while True:
        try:
            processed = await settle_expired_seasons()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Rank season sweep failed; retrying")
            processed = 0
        await asyncio.sleep(1 if processed else 60)


async def run_workers(bot: Bot) -> None:
    """Run database-backed jobs concurrently without duplicating work."""
    async with asyncio.TaskGroup() as task_group:
        if settings.RUNTIME_ROLE in {"combined", "attacks"}:
            task_group.create_task(_rank_worker())
            for worker_id in range(settings.WORKER_COUNT):
                task_group.create_task(_attack_worker(bot, worker_id))
        if settings.RUNTIME_ROLE in {"combined", "bot"}:
            task_group.create_task(run_car_game_ticks(bot))
            task_group.create_task(run_chess_timeouts(bot))
            task_group.create_task(run_tic_tac_toe_timeouts(bot))
            task_group.create_task(run_game_message_cleanup_worker(bot))
            for worker_id in range(settings.NOTIFICATION_WORKER_COUNT):
                task_group.create_task(
                    run_notification_worker(bot, worker_id=worker_id)
                )
