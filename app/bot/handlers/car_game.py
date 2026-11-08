"""Private car-game widget and its authenticated sandbox requests."""

import json
import logging
from typing import cast

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.car_game_widget import HTML
from app.bot.tic_tac_toe_widget import widget_api
from app.core.config import settings
from app.services.car_game_service import CarGameError, act, create_game, state_json
from app.services.school_errors import SchoolUserNotFound
from app.services.user_service import UserInactiveError, UserService

logger = logging.getLogger(__name__)
router = Router(name="car_game")
users = UserService()


@router.callback_query(F.data == "car:open")
async def open_car_game(callback: CallbackQuery, session: AsyncSession) -> None:
    if not settings.TELEGRAM_WIDGET_BETA_ENABLED:
        await callback.answer("ویجت بازی روی این ربات فعال نیست.", show_alert=True)
        return
    message = cast(Message, callback.message)
    if message.chat.type != "private":
        await callback.answer("بازی ماشین فقط در پی‌وی ربات فعاله.", show_alert=True)
        return
    user = await users.get_or_create_from_telegram(session, callback.from_user)
    try:
        game = await create_game(session, user.id)
    except CarGameError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await session.commit()
    response = await widget_api(
        callback.bot,
        "sendWidget",
        {
            "chat_id": callback.from_user.id,
            "html": HTML,
            "width": 320,
            "height": 0,
            "chat_data": state_json(game),
            "allow_queries": True,
        },
    )
    if response is None or not isinstance(response.get("result"), dict):
        game.status = "cancelled"
        await session.commit()
        await callback.answer("ارسال ویجت بازی انجام نشد.", show_alert=True)
        return
    game.message_id = int(response["result"]["message_id"])
    await session.commit()
    await callback.answer()


async def handle_widget_query(payload: dict, bot, session: AsyncSession) -> None:
    query_id = payload.get("id")
    response = "{}"
    game = None
    changed = False
    try:
        namespace, action, raw_id = payload.get("data", "").split(":")
        if namespace != "car" or payload.get("chat", {}).get("type") != "private":
            raise CarGameError("درخواست معتبر نیست.")
        chat_id = payload["chat"]["id"]
        telegram_id = payload["from"]["id"]
        if chat_id != telegram_id:
            raise CarGameError("این بازی برای تو نیست.")
        user = await users.get_active_by_telegram_user_id(session, telegram_id)
        game, crashed = await act(
            session, int(raw_id), user.id, payload["message_id"], action
        )
        changed = action == "start" or crashed
        await session.commit()
        response = state_json(game)
    except (
        KeyError,
        TypeError,
        ValueError,
        SchoolUserNotFound,
        UserInactiveError,
    ) as exc:
        response = json.dumps({"error": str(exc)}, ensure_ascii=False)
    if query_id:
        await widget_api(
            bot,
            "answerWidgetQuery",
            {"widget_query_id": query_id, "data": response},
        )
    if changed and game is not None:
        result = await widget_api(
            bot,
            "editMessageWidgetData",
            {
                "chat_id": payload["chat"]["id"],
                "message_id": game.message_id,
                "chat_data": response,
            },
        )
        if result is None:
            logger.warning("Could not update car widget for game %s", game.id)
