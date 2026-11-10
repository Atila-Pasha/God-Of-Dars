"""Run only the test bot's dispatcher and car worker on a local database."""

import asyncio
from contextlib import suppress

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from sqlalchemy.engine import make_url

from app.bot import create_dispatcher
from app.core.config import settings
from app.db.session import engine
from app.workers.car_game_tick import run_car_game_ticks


async def main() -> None:
    if make_url(settings.DATABASE_URL).host not in {"localhost", "127.0.0.1"}:
        raise SystemExit("Refusing to run local car test against a remote database")
    session = AiohttpSession(
        proxy=settings.TELEGRAM_PROXY,
        limit=settings.TELEGRAM_HTTP_LIMIT,
    )
    async with Bot(settings.BOT_TOKEN, session=session) as bot:
        account = await bot.get_me()
        if account.username != "godofdarstestbot":
            raise SystemExit("Refusing to poll a bot other than @godofdarstestbot")
        dispatcher = create_dispatcher()
        worker = asyncio.create_task(run_car_game_ticks(bot))
        print(f"Local car test ready: @{account.username}", flush=True)
        try:
            await dispatcher.start_polling(
                bot,
                allowed_updates=[
                    *dispatcher.resolve_used_update_types(),
                    "widget_query",
                ],
                close_bot_session=False,
                tasks_concurrency_limit=settings.BOT_CONCURRENCY_LIMIT,
            )
        finally:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
