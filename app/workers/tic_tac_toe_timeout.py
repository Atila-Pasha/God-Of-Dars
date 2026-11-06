"""Resolve expired invitations and turns after restarts as well as live play."""

import asyncio
import logging

from sqlalchemy import select

from app.bot.handlers.tic_tac_toe import (
    publish_board,
    update_invitation_messages,
)
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.tic_tac_toe import TicTacToeGame
from app.services.tic_tac_toe_service import expire_game, now

logger = logging.getLogger(__name__)


async def resolve_timeout(bot, game_id: int, limit: asyncio.Semaphore) -> None:
    async with limit, AsyncSessionLocal() as session:
        game = await expire_game(session, game_id)
        if game is None:
            return
        if game.status == "cancelled":
            await session.commit()
            await update_invitation_messages(
                bot,
                session,
                game,
                "حریفت به درخواست بازی جواب نداد. بازی لغو شد.",
                "وقت پاسخ به درخواست بازی تموم شد.",
            )
        else:
            await publish_board(bot, session, game)


async def run_tic_tac_toe_timeouts(bot) -> None:
    limit = asyncio.Semaphore(
        min(settings.TTT_TIMEOUT_CONCURRENCY, settings.DB_POOL_SIZE)
    )
    while True:
        try:
            async with AsyncSessionLocal() as session:
                ids = (
                    await session.scalars(
                        select(TicTacToeGame.id)
                        .where(
                            TicTacToeGame.status.in_(("invited", "active")),
                            TicTacToeGame.deadline_at <= now(),
                        )
                        .order_by(TicTacToeGame.deadline_at)
                        .limit(settings.TTT_TIMEOUT_BATCH_SIZE)
                    )
                ).all()
            results = await asyncio.gather(
                *(resolve_timeout(bot, game_id, limit) for game_id in ids),
                return_exceptions=True,
            )
            for game_id, result in zip(ids, results, strict=True):
                if isinstance(result, BaseException):
                    logger.error(
                        "Tic-tac-toe timeout failed for game %s",
                        game_id,
                        exc_info=(type(result), result, result.__traceback__),
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Tic-tac-toe timeout sweep failed")
        await asyncio.sleep(1)
