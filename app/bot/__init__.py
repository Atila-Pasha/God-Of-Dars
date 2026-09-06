from aiogram import Dispatcher

from app.bot.custom_emojis import install as install_custom_emojis

install_custom_emojis()

from app.bot.handlers.buffet import router as buffet_router
from app.bot.handlers.battle import router as battle_router
from app.bot.handlers.chance import router as chance_router
from app.bot.handlers.daily import router as daily_router
from app.bot.handlers.library import router as library_router
from app.bot.handlers.mine import router as mine_router
from app.bot.handlers.profile import router as profile_router
from app.bot.handlers.referral import router as referral_router
from app.bot.handlers.school import router as school_router
from app.bot.handlers.start import router as start_router
from app.bot.middlewares.database import DatabaseSessionMiddleware
from app.bot.middlewares.group import GroupAccessMiddleware
from app.bot.middlewares.subscription import SubscriptionMiddleware


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware())
    subscription_middleware = SubscriptionMiddleware()
    dispatcher.message.outer_middleware(subscription_middleware)
    dispatcher.callback_query.outer_middleware(subscription_middleware)
    # Group policy must wrap subscription checks so blocked group commands are
    # ignored before private-only handlers or membership prompts can run.
    dispatcher.message.outer_middleware(GroupAccessMiddleware())
    dispatcher.callback_query.outer_middleware(GroupAccessMiddleware())
    dispatcher.include_router(school_router)
    dispatcher.include_router(buffet_router)
    dispatcher.include_router(battle_router)
    dispatcher.include_router(chance_router)
    dispatcher.include_router(daily_router)
    dispatcher.include_router(library_router)
    dispatcher.include_router(mine_router)
    dispatcher.include_router(profile_router)
    dispatcher.include_router(referral_router)
    dispatcher.include_router(start_router)
    return dispatcher
