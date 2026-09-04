import asyncio
import logging

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot import create_dispatcher
from app.core.config import settings

logger = logging.getLogger(__name__)


async def run_main_bot() -> None:
    dispatcher = create_dispatcher()
    bot_session = (
        AiohttpSession(proxy=settings.TELEGRAM_PROXY, limit=settings.TELEGRAM_HTTP_LIMIT)
        if settings.TELEGRAM_PROXY
        else AiohttpSession(limit=settings.TELEGRAM_HTTP_LIMIT)
    )
    async with Bot(token=settings.BOT_TOKEN, session=bot_session) as bot:
        await dispatcher.start_polling(
            bot,
            tasks_concurrency_limit=settings.BOT_CONCURRENCY_LIMIT,
        )


async def main() -> None:
    tasks = [run_main_bot()]

    if settings.ADMIN_BOT_TOKEN and settings.admin_id_set:
        from admin.main import run_admin_bot

        tasks.append(run_admin_bot())
        logger.info("Admin bot will be started alongside the main bot")
    else:
        logger.warning(
            "Admin bot was not started: configure both ADMIN_BOT_TOKEN and ADMIN_IDS"
        )

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    print("Starting bot...")
    asyncio.run(main())
    print("Bot stopped.")
