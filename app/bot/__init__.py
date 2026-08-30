from aiogram import Dispatcher

from app.bot.handlers.start import router as start_router
from app.bot.middlewares.database import DatabaseSessionMiddleware


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware())
    dispatcher.include_router(start_router)
    return dispatcher
