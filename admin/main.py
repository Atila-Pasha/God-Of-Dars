import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from admin.handlers import router
from app.bot.custom_emojis import install as install_custom_emojis
from app.bot.middlewares.database import DatabaseSessionMiddleware
from app.core.config import settings

install_custom_emojis()


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware())
    dispatcher.include_router(router)
    return dispatcher


async def run_admin_bot() -> None:
    if not settings.ADMIN_BOT_TOKEN:
        raise RuntimeError("ADMIN_BOT_TOKEN is not configured")
    if not settings.admin_id_set:
        raise RuntimeError("ADMIN_IDS is empty; refusing to start an unprotected admin bot")
    session = AiohttpSession(
        proxy=settings.TELEGRAM_PROXY,
        limit=settings.TELEGRAM_HTTP_LIMIT,
    )
    async with Bot(token=settings.ADMIN_BOT_TOKEN, session=session) as bot:
        await create_dispatcher().start_polling(
            bot,
            tasks_concurrency_limit=settings.ADMIN_CONCURRENCY_LIMIT,
        )


async def main() -> None:
    await run_admin_bot()


if __name__ == "__main__":
    asyncio.run(main())
