import asyncio
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from admin.handlers import router
from app.bot.custom_emojis import install as install_custom_emojis
from app.bot.middlewares.database import DatabaseSessionMiddleware
from app.core.config import settings
from app.core.logging import configure_logging

install_custom_emojis()


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware())
    dispatcher.include_router(router)
    return dispatcher


async def run_admin_bot(stop_event: asyncio.Event | None = None) -> None:
    if not settings.ADMIN_BOT_TOKEN:
        raise RuntimeError("ADMIN_BOT_TOKEN is not configured")
    if not settings.admin_id_set:
        raise RuntimeError(
            "ADMIN_IDS is empty; refusing to start an unprotected admin bot"
        )
    session = AiohttpSession(
        proxy=settings.TELEGRAM_PROXY,
        limit=settings.TELEGRAM_HTTP_LIMIT,
    )
    try:
        async with Bot(token=settings.ADMIN_BOT_TOKEN, session=session) as bot:
            dispatcher = create_dispatcher()
            polling_task = asyncio.create_task(
                dispatcher.start_polling(
                    bot,
                    handle_signals=False,
                    close_bot_session=False,
                    tasks_concurrency_limit=settings.ADMIN_CONCURRENCY_LIMIT,
                ),
                name="admin-polling",
            )
            stop_task = (
                asyncio.create_task(stop_event.wait(), name="admin-stop-waiter")
                if stop_event is not None
                else None
            )
            try:
                if stop_task is None:
                    await polling_task
                else:
                    done, _ = await asyncio.wait(
                        (polling_task, stop_task),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if stop_task in done and not polling_task.done():
                        await dispatcher.stop_polling()
                    await polling_task
            finally:
                if stop_task is not None:
                    stop_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await stop_task
                if not polling_task.done():
                    polling_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await polling_task
    finally:
        with suppress(asyncio.CancelledError):
            await session.close()


async def main() -> None:
    await run_admin_bot()


if __name__ == "__main__":
    configure_logging(settings.ENVIRONMENT)
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
