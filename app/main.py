import asyncio

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot import create_dispatcher
from app.core.config import settings


async def main() -> None:
    dispatcher = create_dispatcher()
    bot_session = (
        AiohttpSession(proxy=settings.TELEGRAM_PROXY)
        if settings.TELEGRAM_PROXY
        else None
    )
    async with Bot(token=settings.BOT_TOKEN, session=bot_session) as bot:
        await dispatcher.start_polling(bot)


if __name__ == "__main__":
    print("Starting bot...")
    asyncio.run(main())
    print("Bot stopped.")
