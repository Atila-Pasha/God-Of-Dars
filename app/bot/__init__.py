from aiogram import Dispatcher

from app.bot.handlers.library import router as library_router
from app.bot.handlers.referral import router as referral_router
from app.bot.handlers.school import router as school_router
from app.bot.handlers.start import router as start_router
from app.bot.middlewares.database import DatabaseSessionMiddleware
from app.bot.middlewares.subscription import SubscriptionMiddleware


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware())
    subscription_middleware = SubscriptionMiddleware()
    dispatcher.message.outer_middleware(subscription_middleware)
    dispatcher.callback_query.outer_middleware(subscription_middleware)
    dispatcher.include_router(school_router)
    dispatcher.include_router(library_router)
    dispatcher.include_router(referral_router)
    dispatcher.include_router(start_router)
    return dispatcher
