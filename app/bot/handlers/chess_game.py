"""Private chess invitations and Telegram widget queries."""

from __future__ import annotations

import json
import logging
from contextlib import suppress
from typing import cast

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.formatting import Bold, Text
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.chess_widget import HTML, state_json
from app.bot.handlers.tic_tac_toe import TARGET_PROMPT, edit_flow_message, menu
from app.bot.tic_tac_toe_widget import widget_api
from app.models.chess_game import ChessGame
from app.models.user import User
from app.services.chess_service import (
    ChessError,
    abort_game,
    accept_game,
    cancel_invite,
    create_game,
    move,
)
from app.services.school_errors import SchoolUserNotFound
from app.services.user_service import UserInactiveError, UserService

logger = logging.getLogger(__name__)
router = Router(name="chess_game")
users = UserService()


class ChessFlow(StatesGroup):
    amount = State()
    target = State()


async def _accounts(session: AsyncSession, game: ChessGame) -> tuple[int, int | None]:
    ids = [game.challenger_id] + ([game.opponent_id] if game.opponent_id else [])
    rows = (await session.scalars(select(User).where(User.id.in_(ids)))).all()
    mapping = {row.id: row.telegram_user_id for row in rows}
    return mapping[game.challenger_id], mapping.get(game.opponent_id)


def invitation_text(game: ChessGame, challenger_name: str) -> str:
    stake = (
        f"\nمقدار شرط: {game.stake_amount:,} {'طلا' if game.stake_type == 'coin' else 'الماس'}"
        if game.mode == "wager"
        else ""
    )
    return (
        f"♟ درخواست بازی شطرنج\nاز طرف: {challenger_name}\n"
        f"نوع بازی: {'شرطی' if game.mode == 'wager' else 'دوستانه'}{stake}\n"
        "هر نوبت ۶۰ ثانیه وقت دارد. قبول می‌کنی؟"
    )


def invitation_keyboard(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="قبول می‌کنم",
                    callback_data=f"chess:accept:{game_id}",
                    style="success",
                )
            ],
            [
                InlineKeyboardButton(
                    text="رد می‌کنم",
                    callback_data=f"chess:decline:{game_id}",
                    style="danger",
                )
            ],
        ]
    )


def sent_invitation_keyboard(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="لغو درخواست",
                    callback_data=f"chess:cancel:{game_id}",
                    style="danger",
                )
            ]
        ]
    )


def result_text(game: ChessGame, player_id: int) -> Text:
    result = (
        "بازی مساوی شد."
        if game.winner_id is None
        else "بردی! 🎉"
        if game.winner_id == player_id
        else "باختی!"
    )
    if game.mode != "wager" or game.winner_id is None:
        return Text(Bold(result), "\n", Bold("تغییر موجودی:"), " ۰")
    sign = "+" if game.winner_id == player_id else "−"
    currency = "طلا" if game.stake_type == "coin" else "الماس"
    return Text(
        Bold(result),
        "\n",
        Bold("تغییر موجودی:"),
        f" {sign}{game.stake_amount:,} {currency}",
    )


async def update_invitation_messages(
    bot,
    session: AsyncSession,
    game: ChessGame,
    challenger_text: str,
    opponent_text: str,
) -> None:
    challenger_tg, opponent_tg = await _accounts(session, game)
    await session.commit()
    for chat_id, message_id, content in (
        (challenger_tg, game.challenger_message_id, challenger_text),
        (opponent_tg, game.opponent_message_id, opponent_text),
    ):
        if chat_id is not None and message_id is not None:
            with suppress(TelegramAPIError):
                await edit_flow_message(bot, chat_id, message_id, content)


async def publish_board(bot, session: AsyncSession, game: ChessGame) -> bool:
    """Update both private widgets; a failed initial send leaves no silent match."""
    await session.commit()
    challenger_tg, opponent_tg = await _accounts(session, game)
    data = state_json(game, challenger_tg, opponent_tg)
    if len(data.encode()) > 1024:
        logger.error("Chess widget state too large for game %s", game.id)
        return False
    all_sent = True
    for player_id, chat_id, attr in (
        (game.challenger_id, challenger_tg, "challenger_message_id"),
        (game.opponent_id, opponent_tg, "opponent_message_id"),
    ):
        if player_id is None or chat_id is None:
            continue
        message_id = getattr(game, attr)
        if message_id is None:
            response = await widget_api(
                bot,
                "sendWidget",
                {
                    "chat_id": chat_id,
                    "html": HTML,
                    "width": 0,
                    "height": 0,
                    "chat_data": data,
                    "allow_queries": True,
                },
            )
            if response is not None and isinstance(response.get("result"), dict):
                setattr(game, attr, int(response["result"]["message_id"]))
                await session.commit()
                continue
        else:
            response = await widget_api(
                bot,
                "editMessageWidgetData",
                {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "chat_data": data,
                },
            )
            if response is not None:
                continue
        logger.error(
            "Could not send or update chess widget %s for %s", game.id, chat_id
        )
        all_sent = False
    if game.status == "finished":
        for player_id, chat_id in (
            (game.challenger_id, challenger_tg),
            (game.opponent_id, opponent_tg),
        ):
            if player_id is not None and chat_id is not None:
                with suppress(TelegramAPIError):
                    await bot.send_message(
                        chat_id, **result_text(game, player_id).as_kwargs()
                    )
    return all_sent


@router.callback_query(F.data == "chess:select")
async def select_game(callback: CallbackQuery) -> None:
    message = cast(Message, callback.message)
    await message.edit_text(
        "میخوای با ربات بازی کنی یا حریف واقعی؟",
        reply_markup=menu(
            ("ربات", "chess:computer", "5803143039060808890"),
            ("حریف واقعی", "chess:human", "5258011929993026890"),
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "chess:computer")
async def computer_game(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    message = cast(Message, callback.message)
    await state.clear()
    player = await users.get_or_create_from_telegram(session, callback.from_user)
    try:
        game = await create_game(session, player.id, None, "computer")
    except ChessError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    sent = await publish_board(callback.bot, session, game)
    if not sent:
        await abort_game(session, game.id)
        await message.answer("ارسال ویجت شطرنج انجام نشد؛ بازی لغو شد.")
    else:
        await message.answer("بازی شطرنج با ربات شروع شد. تو سفید هستی و نوبت توئه!")
    await callback.answer()


@router.callback_query(F.data == "chess:human")
async def human_game(callback: CallbackQuery) -> None:
    message = cast(Message, callback.message)
    await message.answer(
        "میخوای دوستانه بازی کنی یا شرطی؟",
        reply_markup=menu(
            ("دوستانه", "chess:friendly", "5944970130554359187"),
            ("شرطی", "chess:wager", "5255934553096202209"),
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "chess:friendly")
async def friendly_game(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ChessFlow.target)
    await state.update_data(mode="friendly", currency=None, amount=0)
    await cast(Message, callback.message).answer(**TARGET_PROMPT.as_kwargs())
    await callback.answer()


@router.callback_query(F.data == "chess:wager")
async def wager_game(callback: CallbackQuery) -> None:
    await cast(Message, callback.message).edit_text(
        "میخوای با طلا شرط ببندی یا الماس؟",
        reply_markup=menu(
            ("طلا", "chess:currency:coin", "5825699971076202989"),
            ("الماس", "chess:currency:diamond", "5235630047959727475"),
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chess:currency:"))
async def currency_game(callback: CallbackQuery, state: FSMContext) -> None:
    currency = (callback.data or "").split(":")[-1]
    if currency not in {"coin", "diamond"}:
        await callback.answer("این گزینه معتبر نیست.", show_alert=True)
        return
    await state.set_state(ChessFlow.amount)
    await state.update_data(mode="wager", currency=currency)
    await cast(Message, callback.message).answer(
        f"چقدر {'طلا' if currency == 'coin' else 'الماس'} میخوای شرط ببندی؟ عددش رو بفرست."
    )
    await callback.answer()


@router.message(ChessFlow.amount, F.chat.type == "private")
async def amount_game(message: Message, state: FSMContext) -> None:
    raw = (
        (message.text or "")
        .translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
        .replace(",", "")
        .strip()
    )
    if (
        not raw.isascii()
        or not raw.isdecimal()
        or int(raw) < 1
        or int(raw) > 1_000_000_000
    ):
        await message.answer(
            "مقدار شرط باید یه عدد مثبت تا یک میلیارد باشه. دوباره بفرست."
        )
        return
    await state.update_data(amount=int(raw))
    await state.set_state(ChessFlow.target)
    await message.answer(**TARGET_PROMPT.as_kwargs())


@router.message(ChessFlow.target, F.chat.type == "private")
async def target_game(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    bot, telegram_user = message.bot, message.from_user
    if bot is None or telegram_user is None:
        return
    details = await state.get_data()
    target = (message.text or "").strip()
    if not target or target.startswith("/"):
        await message.answer("آیدی حریف رو به شکل @username یا آیدی عددی بفرست. 🆔")
        return
    if target.isascii() and target.isdecimal():
        opponent = await session.scalar(
            select(User).where(
                User.telegram_user_id == int(target), User.is_active.is_(True)
            )
        )
    else:
        opponent = await session.scalar(
            select(User).where(
                func.lower(User.username) == target.lstrip("@").casefold(),
                User.is_active.is_(True),
            )
        )
    if opponent is None:
        await message.answer(
            "حریف رو پیدا نکردم. باید قبلاً ربات رو توی پی‌وی استارت کرده باشه. 🆔"
        )
        return
    player = await users.get_or_create_from_telegram(session, telegram_user)
    try:
        game = await create_game(
            session,
            player.id,
            opponent.id,
            details["mode"],
            details.get("currency"),
            details.get("amount", 0),
        )
    except (KeyError, ChessError) as exc:
        await message.answer(str(exc))
        return
    await session.commit()
    try:
        sent = await bot.send_message(
            opponent.telegram_user_id,
            invitation_text(game, player.first_name),
            reply_markup=invitation_keyboard(game.id),
        )
    except TelegramAPIError:
        await cancel_invite(session, game.id, player.id)
        await session.commit()
        await message.answer(
            "نتونستم درخواست رو بفرستم. حریف باید ربات رو توی پی‌وی استارت کرده باشه."
        )
        await state.clear()
        return
    pending = await message.answer(
        "درخواستت رو ارسال کردم. منتظر بمون. بهت خبر میدم.",
        reply_markup=sent_invitation_keyboard(game.id),
    )
    game.challenger_message_id, game.opponent_message_id = (
        pending.message_id,
        sent.message_id,
    )
    await session.commit()
    await state.clear()


@router.callback_query(F.data.startswith("chess:accept:"))
async def accept_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        game_id = int((callback.data or "").rsplit(":", 1)[-1])
        opponent = await users.get_active_by_telegram_user_id(
            session, callback.from_user.id
        )
        game = await accept_game(session, game_id, opponent.id)
    except (ValueError, ChessError, SchoolUserNotFound, UserInactiveError):
        await callback.answer("این دعوت دیگر فعال نیست.", show_alert=True)
        return
    if game.status == "cancelled":
        await session.commit()
        await update_invitation_messages(
            callback.bot,
            session,
            game,
            "بازی لغو شد. یکی از شما موجودی کافی برای شرط رو نداره.",
            "بازی لغو شد. یکی از شما موجودی کافی برای شرط رو نداره.",
        )
    else:
        await session.commit()
        await update_invitation_messages(
            callback.bot,
            session,
            game,
            "حریفت قبول کرد. بازی شروع شد! تو سفید هستی.",
            "بازی شروع شد! تو سیاه هستی و منتظر حرکت حریف بمان.",
        )
        game.challenger_message_id = None
        game.opponent_message_id = None
        sent = await publish_board(callback.bot, session, game)
        if not sent:
            await abort_game(session, game.id)
            await publish_board(callback.bot, session, game)
            challenger_tg, opponent_tg = await _accounts(session, game)
            for chat_id in (challenger_tg, opponent_tg):
                if chat_id is not None:
                    with suppress(TelegramAPIError):
                        await callback.bot.send_message(
                            chat_id, "ارسال ویجت شطرنج انجام نشد؛ بازی و شرط آن لغو شد."
                        )
    await callback.answer()


@router.callback_query(F.data.startswith("chess:decline:"))
async def decline_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        game_id = int((callback.data or "").rsplit(":", 1)[-1])
        user = await users.get_active_by_telegram_user_id(
            session, callback.from_user.id
        )
        game = await cancel_invite(session, game_id, user.id, by_challenger=False)
    except (ValueError, ChessError, SchoolUserNotFound, UserInactiveError):
        await callback.answer("این دعوت دیگر فعال نیست.", show_alert=True)
        return
    await session.commit()
    await update_invitation_messages(
        callback.bot,
        session,
        game,
        "حریفت درخواست بازی رو رد کرد.",
        "درخواست بازی رو رد کردی.",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chess:cancel:"))
async def cancel_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    bot = cast(Bot, callback.bot)
    try:
        game_id = int((callback.data or "").rsplit(":", 1)[-1])
        user = await users.get_active_by_telegram_user_id(
            session, callback.from_user.id
        )
        game = await cancel_invite(session, game_id, user.id, by_challenger=True)
    except (ValueError, ChessError, SchoolUserNotFound, UserInactiveError):
        await callback.answer("این دعوت دیگر فعال نیست.", show_alert=True)
        return
    await session.commit()
    challenger_tg, opponent_tg = await _accounts(session, game)
    if game.challenger_message_id is not None:
        with suppress(TelegramAPIError):
            await edit_flow_message(
                bot,
                challenger_tg,
                game.challenger_message_id,
                "درخواست بازی را لغو کردی.",
            )
    deleted = False
    if opponent_tg is not None and game.opponent_message_id is not None:
        try:
            deleted = await bot.delete_message(opponent_tg, game.opponent_message_id)
        except TelegramAPIError:
            logger.warning("Could not delete cancelled chess invitation %s", game.id)
        if not deleted:
            with suppress(TelegramAPIError):
                await edit_flow_message(
                    bot, opponent_tg, game.opponent_message_id, "درخواست بازی لغو شد."
                )
    await callback.answer(
        "درخواست لغو شد."
        if deleted
        else "درخواست لغو شد، ولی حذف پیام حریف انجام نشد.",
        show_alert=not deleted,
    )


async def handle_widget_query(payload: dict, bot, session: AsyncSession) -> None:
    query_id = payload.get("id")
    result = "{}"
    try:
        namespace, verb, raw_id, uci = payload.get("data", "").split(":")
        if (
            namespace != "chess"
            or verb != "move"
            or payload.get("chat", {}).get("type") != "private"
        ):
            raise ChessError("درخواست معتبر نیست.")
        game_id = int(raw_id)
        game = await session.get(ChessGame, game_id)
        if game is None:
            raise ChessError("بازی رو پیدا نکردم.")
        chat_id, message_id, actor_tg = (
            payload["chat"]["id"],
            payload["message_id"],
            payload["from"]["id"],
        )
        challenger_tg, opponent_tg = await _accounts(session, game)
        if chat_id != actor_tg or (chat_id, message_id) not in (
            (challenger_tg, game.challenger_message_id),
            (opponent_tg, game.opponent_message_id),
        ):
            raise ChessError("پیام بازی معتبر نیست.")
        actor = await users.get_active_by_telegram_user_id(session, actor_tg)
        game = await move(session, game_id, actor.id, uci)
        await session.commit()
        result = state_json(game, challenger_tg, opponent_tg)
        if query_id:
            await widget_api(
                bot, "answerWidgetQuery", {"widget_query_id": query_id, "data": result}
            )
            query_id = None
        await publish_board(bot, session, game)
    except (
        KeyError,
        AttributeError,
        TypeError,
        ValueError,
        ChessError,
        SchoolUserNotFound,
        UserInactiveError,
    ) as exc:
        result = json.dumps({"error": str(exc)}, ensure_ascii=False)
    if query_id:
        await widget_api(
            bot, "answerWidgetQuery", {"widget_query_id": query_id, "data": result}
        )
