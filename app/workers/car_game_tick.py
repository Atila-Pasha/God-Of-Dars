"""Advance active car runs and pay rewards after server-observed collisions."""

import asyncio
import logging

from sqlalchemy import select

from app.bot.tic_tac_toe_widget import widget_api
from app.db.session import AsyncSessionLocal
from app.models.car_game import CarGame
from app.services.car_game_service import now, settle_due_game, state_json

logger = logging.getLogger(__name__)


async def _resolve_one(bot, game_id: int, limit: asyncio.Semaphore) -> None:
    async with limit, AsyncSessionLocal() as session:
        game = await settle_due_game(session, game_id)
        await session.commit()
        if game is not None and game.message_id is not None:
            result = await session.scalar(
                select(CarGame.user_id).where(CarGame.id == game_id)
            )
            if result is None:
                return
            from app.models.user import User

            chat_id = await session.scalar(
                select(User.telegram_user_id).where(User.id == result)
            )
            if chat_id is not None:
                await widget_api(
                    bot,
                    "editMessageWidgetData",
                    {
                        "chat_id": chat_id,
                        "message_id": game.message_id,
                        "chat_data": state_json(game),
                    },
                )


async def run_car_game_ticks(bot) -> None:
    limit = asyncio.Semaphore(6)
    while True:
        try:
            async with AsyncSessionLocal() as session:
                ids = (
                    await session.scalars(
                        select(CarGame.id)
                        .where(
                            CarGame.status == "active", CarGame.next_tick_at <= now()
                        )
                        .order_by(CarGame.next_tick_at)
                        .limit(100)
                    )
                ).all()
            results = await asyncio.gather(
                *(_resolve_one(bot, game_id, limit) for game_id in ids),
                return_exceptions=True,
            )
            for game_id, result in zip(ids, results, strict=True):
                if isinstance(result, BaseException):
                    logger.error(
                        "Car game tick failed for %s",
                        game_id,
                        exc_info=(type(result), result, result.__traceback__),
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Car game tick sweep failed")
        await asyncio.sleep(0.25)
