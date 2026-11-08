"""Private /game flow, invitation callbacks, and widget move queries."""

from __future__ import annotations

import json
import logging
from contextlib import suppress
from typing import cast

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.formatting import Bold, CustomEmoji, Text
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.advanced_tic_tac_toe_widget import HTML as ADVANCED_HTML
from app.bot.tic_tac_toe_widget import (
    HTML,
    fallback_keyboard,
    fallback_text,
    state_json,
    widget_api,
)
from app.core.config import settings
from app.models.tic_tac_toe import TicTacToeGame
from app.models.user import User
from app.services.tic_tac_toe_service import (
    GameError,
    abort_game,
    accept_game,
    cancel_invite,
    create_game,
    move,
)
from app.services.user_service import UserService

logger = logging.getLogger(__name__)
router = Router(name="tic_tac_toe")
users = UserService()


class GameFlow(StatesGroup):
    amount = State()
    target = State()


def menu(*rows: tuple[str, str, str | None]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label, callback_data=data, icon_custom_emoji_id=icon
                )
            ]
            for label, data, icon in rows
        ]
    )


TARGET_PROMPT = Text(
    "آیدی حریف رو بفرست. @username یا آیدی عددی تلگرام. "
    "حریف باید قبلاً ربات رو استارت کرده باشه. ",
    CustomEmoji("🆔", custom_emoji_id="5845880789744488517"),
)


async def edit_flow_message(
    bot, chat_id: int, message_id: int, content: str | Text
) -> None:
    rendered = content.as_kwargs() if isinstance(content, Text) else {"text": content}
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, **rendered)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


async def update_invitation_messages(
    bot,
    session: AsyncSession,
    game: TicTacToeGame,
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


async def _accounts(
    session: AsyncSession, game: TicTacToeGame
) -> tuple[int, int | None]:
    ids = [game.challenger_id] + ([game.opponent_id] if game.opponent_id else [])
    rows = (await session.scalars(select(User).where(User.id.in_(ids)))).all()
    mapping = {row.id: row.telegram_user_id for row in rows}
    opponent_tg = (
        mapping.get(game.opponent_id) if game.opponent_id is not None else None
    )
    return mapping[game.challenger_id], opponent_tg


def result_text(game: TicTacToeGame, player_id: int) -> Text:
    if game.winner_id is None:
        outcome = Text(Bold("بازی مساوی شد."))
    elif game.winner_id == player_id:
        outcome = Text(
            Bold("بردی! "),
            CustomEmoji("🎉", custom_emoji_id="5832496894261071430"),
        )
    else:
        outcome = Text(
            Bold("باختی! "),
            CustomEmoji("😢", custom_emoji_id="5823187398028168504"),
        )
    if game.mode != "wager" or game.winner_id is None:
        return Text(outcome, "\n", Bold("تغییر موجودی:"), " ۰")
    currency = "طلا" if game.stake_type == "coin" else "الماس"
    sign = "+" if game.winner_id == player_id else "−"
    return Text(
        outcome,
        "\n",
        Bold("تغییر موجودی:"),
        f" {sign}{game.stake_amount:,} {currency}",
    )


def invitation_text(game: TicTacToeGame, challenger_name: str) -> Text:
    parts = [
        f"درخواست بازی {'دوز پیشرفته' if game.variant == 'advanced' else 'دوز'} ",
        CustomEmoji("🎮", custom_emoji_id="4972415571384599106"),
        "\nاسم حریف: ",
        challenger_name,
        "\nنوع بازی: ",
        "شرطی" if game.mode == "wager" else "دوستانه",
    ]
    if game.mode == "wager":
        parts.extend(
            (
                "\nمقدار شرط: ",
                f"{game.stake_amount:,} ",
                "طلا " if game.stake_type == "coin" else "الماس ",
                CustomEmoji(
                    "🪙" if game.stake_type == "coin" else "💎",
                    custom_emoji_id="5825699971076202989"
                    if game.stake_type == "coin"
                    else "5235630047959727475",
                ),
            )
        )
    if game.variant == "advanced":
        size = "۱۰×۱۰" if len(game.board) == 100 else "۱۵×۱۵"
        parts.append(f"\nقانون: پنج مهرهٔ پشت سر هم روی صفحهٔ {size}.")
    parts.append("\nقبول میکنی؟")
    return Text(*parts)


def invitation_keyboard(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="قبول می‌کنم",
                    callback_data=f"ttt:accept:{game_id}",
                    style="success",
                )
            ],
            [
                InlineKeyboardButton(
                    text="رد می‌کنم",
                    callback_data=f"ttt:decline:{game_id}",
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
                    callback_data=f"ttt:cancel:{game_id}",
                    style="danger",
                )
            ]
        ]
    )


async def publish_board(bot, session: AsyncSession, game: TicTacToeGame) -> bool:
    """Persist the game before talking to Telegram, then record message IDs."""
    await session.commit()
    challenger_tg, opponent_tg = await _accounts(session, game)
    await session.commit()
    state = state_json(game, challenger_tg, opponent_tg)
    data_key = "chat_data" if game.variant == "advanced" else "public_data"
    all_sent = True
    for user_id, chat_id, message_attr, widget_attr in (
        (
            game.challenger_id,
            challenger_tg,
            "challenger_message_id",
            "challenger_widget",
        ),
        (game.opponent_id, opponent_tg, "opponent_message_id", "opponent_widget"),
    ):
        if user_id is None or chat_id is None:
            continue
        message_id = getattr(game, message_attr)
        is_widget = getattr(game, widget_attr)
        if message_id is not None and is_widget:
            response = await widget_api(
                bot,
                "editMessageWidgetData",
                {"chat_id": chat_id, "message_id": message_id, data_key: state},
            )
            if response is not None:
                continue
            if game.variant == "advanced":
                logger.error(
                    "Could not update advanced game widget %s for %s", game.id, chat_id
                )
                all_sent = False
                continue
        if game.variant == "advanced" and message_id is not None:
            logger.error(
                "Advanced game %s has a non-widget message for %s", game.id, chat_id
            )
            all_sent = False
            continue
        if message_id is not None and not is_widget:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=fallback_text(game, user_id),
                    reply_markup=fallback_keyboard(game, user_id),
                )
                continue
            except TelegramAPIError:
                pass
        if message_id is None:
            response = await widget_api(
                bot,
                "sendWidget",
                {
                    "chat_id": chat_id,
                    "html": ADVANCED_HTML if game.variant == "advanced" else HTML,
                    "width": 320 if game.variant == "advanced" else 300,
                    "height": 0,
                    data_key: state,
                    "allow_queries": True,
                },
            )
            if response is not None:
                setattr(game, message_attr, int(response["result"]["message_id"]))
                setattr(game, widget_attr, True)
                await session.commit()
                continue
        if game.variant == "advanced":
            logger.error(
                "Could not send advanced game widget %s to %s", game.id, chat_id
            )
            all_sent = False
            continue
        try:
            sent = await bot.send_message(
                chat_id,
                fallback_text(game, user_id),
                reply_markup=fallback_keyboard(game, user_id),
            )
            setattr(game, message_attr, sent.message_id)
            setattr(game, widget_attr, False)
            await session.commit()
        except TelegramAPIError:
            logger.warning("Could not send tic-tac-toe board to %s", chat_id)
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


@router.message(Command("game"), F.chat.type.in_({"group", "supergroup"}))
async def game_group(message: Message) -> None:
    await message.reply("🎮 بازی فقط توی پی‌وی ربات فعاله. بیا پی‌وی و /game رو بزن.")


@router.message(Command("game"), F.chat.type == "private")
async def game_private(message: Message, state: FSMContext) -> None:
    await state.clear()
    content = Text(
        "یکی از بازی هارو انتخاب کن ",
        CustomEmoji("🎮", custom_emoji_id="4972415571384599106"),
    )
    rendered = content.as_kwargs()
    text = rendered.pop("text")
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="دوز",
                        callback_data="ttt:select",
                        icon_custom_emoji_id="5222158908805632010",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="دوز پیشرفته",
                        callback_data="ttt:select:advanced",
                        icon_custom_emoji_id="5222158908805632010",
                    )
                ],
            ]
        ),
        **rendered,
    )


@router.callback_query(F.data.in_({"ttt:select", "ttt:select:advanced"}))
async def select_game(callback: CallbackQuery) -> None:
    message = cast(Message, callback.message)
    suffix = ":advanced" if (callback.data or "").endswith(":advanced") else ""
    await message.edit_text(
        "میخوای با ربات بازی کنی یا حریف واقعی؟",
        reply_markup=menu(
            ("ربات", f"ttt:computer{suffix}", "5803143039060808890"),
            ("حریف واقعی", f"ttt:human{suffix}", "5258011929993026890"),
        ),
    )
    await callback.answer()


@router.callback_query(F.data.in_({"ttt:computer", "ttt:computer:advanced"}))
async def computer_game(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    message = cast(Message, callback.message)
    await state.clear()
    if (callback.data or "").endswith(
        ":advanced"
    ) and not settings.TELEGRAM_WIDGET_BETA_ENABLED:
        await callback.answer("ویجت بازی روی این ربات فعال نیست.", show_alert=True)
        return
    player = await users.get_or_create_from_telegram(session, callback.from_user)
    try:
        variant = (
            "advanced" if (callback.data or "").endswith(":advanced") else "classic"
        )
        game = await create_game(session, player.id, None, "computer", variant=variant)
    except GameError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await message.answer("بازی با ربات شروع شد. نوبت توئه!")
    sent = await publish_board(callback.bot, session, game)
    if variant == "advanced" and sent is False:
        await abort_game(session, game.id)
        await publish_board(callback.bot, session, game)
        await message.answer("ارسال ویجت بازی انجام نشد؛ بازی لغو شد.")
    await callback.answer()


@router.callback_query(F.data.in_({"ttt:human", "ttt:human:advanced"}))
async def human_game(callback: CallbackQuery) -> None:
    message = cast(Message, callback.message)
    suffix = ":advanced" if (callback.data or "").endswith(":advanced") else ""
    await message.answer(
        "میخوای دوستانه بازی کنی یا شرطی؟",
        reply_markup=menu(
            ("دوستانه", f"ttt:friendly{suffix}", "5944970130554359187"),
            ("شرطی", f"ttt:wager{suffix}", "5255934553096202209"),
        ),
    )
    await callback.answer()


@router.callback_query(F.data.in_({"ttt:friendly", "ttt:friendly:advanced"}))
async def friendly_game(callback: CallbackQuery, state: FSMContext) -> None:
    message = cast(Message, callback.message)
    if (callback.data or "").endswith(
        ":advanced"
    ) and not settings.TELEGRAM_WIDGET_BETA_ENABLED:
        await callback.answer("ویجت بازی روی این ربات فعال نیست.", show_alert=True)
        return
    await state.set_state(GameFlow.target)
    if (callback.data or "").endswith(":advanced"):
        await state.update_data(
            mode="friendly", currency=None, amount=0, variant="advanced"
        )
    else:
        await state.update_data(mode="friendly", currency=None, amount=0)
    await message.answer(**TARGET_PROMPT.as_kwargs())
    await callback.answer()


@router.callback_query(F.data.in_({"ttt:wager", "ttt:wager:advanced"}))
async def wager_game(callback: CallbackQuery) -> None:
    message = cast(Message, callback.message)
    if (callback.data or "").endswith(
        ":advanced"
    ) and not settings.TELEGRAM_WIDGET_BETA_ENABLED:
        await callback.answer("ویجت بازی روی این ربات فعال نیست.", show_alert=True)
        return
    suffix = ":advanced" if (callback.data or "").endswith(":advanced") else ""
    await message.edit_text(
        "میخوای با طلا شرط ببندی یا الماس؟",
        reply_markup=menu(
            ("طلا", f"ttt:currency:coin{suffix}", "5825699971076202989"),
            ("الماس", f"ttt:currency:diamond{suffix}", "5235630047959727475"),
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ttt:currency:"))
async def currency_game(callback: CallbackQuery, state: FSMContext) -> None:
    message = cast(Message, callback.message)
    parts = (callback.data or "").split(":")
    currency = parts[2] if len(parts) >= 3 else ""
    if currency not in {"coin", "diamond"}:
        await callback.answer("این گزینه معتبر نیست.", show_alert=True)
        return
    await state.set_state(GameFlow.amount)
    if len(parts) == 4 and parts[3] == "advanced":
        await state.update_data(mode="wager", currency=currency, variant="advanced")
    else:
        await state.update_data(mode="wager", currency=currency)
    await message.answer(
        f"چقدر {'طلا' if currency == 'coin' else 'الماس'} میخوای شرط ببندی؟ عددش رو بفرست."
    )
    await callback.answer()


@router.message(GameFlow.amount, F.chat.type == "private")
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
    await state.set_state(GameFlow.target)
    await message.answer(**TARGET_PROMPT.as_kwargs())


@router.message(GameFlow.target, F.chat.type == "private")
async def target_game(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    bot = message.bot
    telegram_user = message.from_user
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
            details.get("variant", "classic"),
        )
    except GameError as exc:
        await message.answer(str(exc))
        return
    await session.commit()
    try:
        sent = await bot.send_message(
            opponent.telegram_user_id,
            reply_markup=invitation_keyboard(game.id),
            **invitation_text(game, player.first_name).as_kwargs(),
        )
    except TelegramAPIError:
        await cancel_invite(session, game.id, player.id)
        await session.commit()
        await message.answer(
            "نتونستم درخواست رو بفرستم. حریف باید ربات رو توی پی‌وی استارت کرده باشه.",
        )
        await state.clear()
        return
    pending = await message.answer(
        "درخواستت رو ارسال کردم. منتظر بمون. بهت خبر میدم.",
        reply_markup=sent_invitation_keyboard(game.id),
    )
    game.challenger_message_id = pending.message_id
    game.opponent_message_id = sent.message_id
    await session.commit()
    await state.clear()


@router.callback_query(F.data.startswith("ttt:accept:"))
async def accept_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        game_id = int((callback.data or "").rsplit(":", 1)[-1])
        opponent = await users.get_active_by_telegram_user_id(
            session, callback.from_user.id
        )
        game = await accept_game(session, game_id, opponent.id)
    except (ValueError, GameError):
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
            "حریفت قبول کرد. بازی شروع شد! نوبت توئه.",
            "بازی شروع شد! منتظر حرکت حریفت باش.",
        )
        game.challenger_message_id = None
        game.opponent_message_id = None
        sent = await publish_board(callback.bot, session, game)
        if game.variant == "advanced" and sent is False:
            await abort_game(session, game.id)
            await publish_board(callback.bot, session, game)
            challenger_tg, opponent_tg = await _accounts(session, game)
            bot = callback.bot
            for chat_id in (challenger_tg, opponent_tg):
                if chat_id is not None and bot is not None:
                    with suppress(TelegramAPIError):
                        await bot.send_message(
                            chat_id, "ارسال ویجت بازی انجام نشد؛ بازی و شرط آن لغو شد."
                        )
    await callback.answer()


@router.callback_query(F.data.startswith("ttt:decline:"))
async def decline_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        game_id = int((callback.data or "").rsplit(":", 1)[-1])
        user = await users.get_active_by_telegram_user_id(
            session, callback.from_user.id
        )
        game = await cancel_invite(session, game_id, user.id, by_challenger=False)
    except (ValueError, GameError):
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


@router.callback_query(F.data.startswith("ttt:cancel:"))
async def cancel_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    bot = cast(Bot, callback.bot)
    try:
        game_id = int((callback.data or "").rsplit(":", 1)[-1])
        user = await users.get_active_by_telegram_user_id(
            session, callback.from_user.id
        )
        game = await cancel_invite(session, game_id, user.id, by_challenger=True)
    except (ValueError, GameError):
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
            logger.warning("Could not delete cancelled invitation %s", game.id)
        if not deleted:
            with suppress(TelegramAPIError):
                await edit_flow_message(
                    bot,
                    opponent_tg,
                    game.opponent_message_id,
                    "درخواست بازی لغو شد.",
                )
    await callback.answer(
        "درخواست لغو شد."
        if deleted
        else "درخواست لغو شد، ولی حذف پیام حریف انجام نشد.",
        show_alert=not deleted,
    )


@router.callback_query(F.data.startswith("ttt:move:"))
async def move_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        _, _, game_id, cell = (callback.data or "").split(":")
        user = await users.get_active_by_telegram_user_id(
            session, callback.from_user.id
        )
        game = await move(session, int(game_id), user.id, int(cell))
    except (ValueError, GameError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await publish_board(callback.bot, session, game)
    await callback.answer()


@router.callback_query(F.data == "ttt:noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer("این خانه قابل انتخاب نیست.")


async def handle_widget_query(payload: dict, bot, session: AsyncSession) -> None:
    query_id = payload.get("id")
    result = "{}"
    try:
        data = payload.get("data", "")
        verb, raw_id, raw_cell = data.split(":")
        if verb != "move" or payload.get("chat", {}).get("type") != "private":
            raise GameError("درخواست نامعتبر است.")
        game_id, cell = int(raw_id), int(raw_cell)
        game = await session.get(TicTacToeGame, game_id)
        if game is None:
            raise GameError("بازی رو پیدا نکردم.")
        chat_id = payload["chat"]["id"]
        message_id = payload["message_id"]
        actor_tg = payload["from"]["id"]
        challenger_tg, opponent_tg = await _accounts(session, game)
        if (chat_id, message_id) not in (
            (challenger_tg, game.challenger_message_id),
            (opponent_tg, game.opponent_message_id),
        ) or chat_id != actor_tg:
            raise GameError("پیام بازی معتبر نیست.")
        actor = await users.get_active_by_telegram_user_id(session, actor_tg)
        game = await move(session, game_id, actor.id, cell)
        await session.commit()
        result = state_json(game, challenger_tg, opponent_tg)
        if query_id:
            await widget_api(
                bot, "answerWidgetQuery", {"widget_query_id": query_id, "data": result}
            )
            query_id = None
        await publish_board(bot, session, game)
    except (KeyError, AttributeError, TypeError, ValueError, GameError) as exc:
        result = json.dumps({"error": str(exc)}, ensure_ascii=False)
    if query_id:
        await widget_api(
            bot, "answerWidgetQuery", {"widget_query_id": query_id, "data": result}
        )
