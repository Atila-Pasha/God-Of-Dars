import asyncio
import logging
import signal
from contextlib import suppress

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot import create_dispatcher
from app.core.config import settings
from app.core.logging import configure_logging
from app.workers.runtime import run_workers

logger = logging.getLogger(__name__)


async def run_main_bot(stop_event: asyncio.Event) -> None:
    dispatcher = create_dispatcher()
    bot_session = (
        AiohttpSession(
            proxy=settings.TELEGRAM_PROXY, limit=settings.TELEGRAM_HTTP_LIMIT
        )
        if settings.TELEGRAM_PROXY
        else AiohttpSession(limit=settings.TELEGRAM_HTTP_LIMIT)
    )
    async with Bot(token=settings.BOT_TOKEN, session=bot_session) as bot:
        worker_task = asyncio.create_task(
            run_workers(bot),
            name="attack-workers",
        )
        polling_task = asyncio.create_task(
            dispatcher.start_polling(
                bot,
                handle_signals=False,
                close_bot_session=False,
                tasks_concurrency_limit=settings.BOT_CONCURRENCY_LIMIT,
            ),
            name="main-polling",
        )
        stop_task = asyncio.create_task(stop_event.wait(), name="main-stop-waiter")
        try:
            done, _ = await asyncio.wait(
                (polling_task, worker_task, stop_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if (stop_task in done or worker_task in done) and not polling_task.done():
                await dispatcher.stop_polling()
            await polling_task
            if worker_task.done():
                # Do not silently keep polling if the worker task group exits
                # or crashes unexpectedly.
                await worker_task
        finally:
            stop_task.cancel()
            with suppress(asyncio.CancelledError):
                await stop_task
            if not polling_task.done():
                polling_task.cancel()
                with suppress(asyncio.CancelledError):
                    await polling_task
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task


async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(shutdown_signal, stop_event.set)

    tasks = [asyncio.create_task(run_main_bot(stop_event), name="main-bot")]

    if settings.ADMIN_BOT_TOKEN and settings.admin_id_set:
        from admin.main import run_admin_bot

        tasks.append(
            asyncio.create_task(
                run_admin_bot(stop_event),
                name="admin-bot",
            )
        )
        logger.info("Admin bot will be started alongside the main bot")
    else:
        logger.warning(
            "Admin bot was not started: configure both ADMIN_BOT_TOKEN and ADMIN_IDS"
        )

    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.remove_signal_handler(shutdown_signal)


if __name__ == "__main__":
    configure_logging(settings.ENVIRONMENT)
    logger.info("Starting bot")
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
    logger.info("Bot stopped")
