from aiogram import Dispatcher

from app.bot.custom_emojis import install as install_custom_emojis
from app.bot.handlers.archers import router as archer_router
from app.bot.handlers.battle import router as battle_router
from app.bot.handlers.buffet import router as buffet_router
from app.bot.handlers.car_game import handle_widget_query as handle_car_widget_query
from app.bot.handlers.car_game import router as car_game_router
from app.bot.handlers.chance import router as chance_router
from app.bot.handlers.chess_game import handle_widget_query as handle_chess_widget_query
from app.bot.handlers.chess_game import router as chess_game_router
from app.bot.handlers.daily import router as daily_router
from app.bot.handlers.leaderboard import router as leaderboard_router
from app.bot.handlers.library import router as library_router
from app.bot.handlers.mine import router as mine_router
from app.bot.handlers.profile import router as profile_router
from app.bot.handlers.quick import router as quick_router
from app.bot.handlers.referral import router as referral_router
from app.bot.handlers.school import router as school_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.tic_tac_toe import handle_widget_query
from app.bot.handlers.tic_tac_toe import router as tic_tac_toe_router
from app.bot.isolation import UserEventIsolation
from app.bot.middlewares.database import DatabaseSessionMiddleware
from app.bot.middlewares.group import GroupAccessMiddleware
from app.bot.middlewares.navigation import NavigationStateMiddleware
from app.bot.middlewares.subscription import SubscriptionMiddleware


class GameDispatcher(Dispatcher):
    async def _listen_update(self, update, **kwargs):
        payload = (update.model_extra or {}).get("widget_query")
        if payload is not None:
            if (payload.get("data") or "").startswith("car:"):
                await handle_car_widget_query(payload, kwargs["bot"], kwargs["session"])
            elif (payload.get("data") or "").startswith("chess:"):
                await handle_chess_widget_query(
                    payload, kwargs["bot"], kwargs["session"]
                )
            else:
                await handle_widget_query(payload, kwargs["bot"], kwargs["session"])
            return None
        return await super()._listen_update(update, **kwargs)


def create_dispatcher() -> Dispatcher:
    install_custom_emojis()
    dispatcher = GameDispatcher(events_isolation=UserEventIsolation())
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware())
    subscription_middleware = SubscriptionMiddleware()
    group_middleware = GroupAccessMiddleware()
    # Group policy must wrap subscription checks so blocked group commands are
    # ignored before private-only handlers or membership prompts can run.
    dispatcher.message.outer_middleware(group_middleware)
    dispatcher.callback_query.outer_middleware(group_middleware)
    dispatcher.chat_member.outer_middleware(group_middleware)
    dispatcher.my_chat_member.outer_middleware(group_middleware)
    dispatcher.message.outer_middleware(subscription_middleware)
    dispatcher.callback_query.outer_middleware(subscription_middleware)
    dispatcher.message.outer_middleware(NavigationStateMiddleware())
    # Explicit leaderboard commands and group phrases must win over generic
    # text handlers used by active FSM flows such as question answers.
    dispatcher.include_router(quick_router)
    dispatcher.include_router(car_game_router)
    dispatcher.include_router(chess_game_router)
    dispatcher.include_router(tic_tac_toe_router)
    dispatcher.include_router(leaderboard_router)
    dispatcher.include_router(school_router)
    dispatcher.include_router(buffet_router)
    dispatcher.include_router(archer_router)
    dispatcher.include_router(battle_router)
    dispatcher.include_router(profile_router)
    dispatcher.include_router(chance_router)
    dispatcher.include_router(daily_router)
    dispatcher.include_router(library_router)
    dispatcher.include_router(mine_router)
    dispatcher.include_router(referral_router)
    dispatcher.include_router(start_router)
    return dispatcher
