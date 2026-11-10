"""Telegram message widget and an inline-keyboard compatibility board."""

from __future__ import annotations

import asyncio
import json
import logging
import zlib
from datetime import UTC
from typing import Any

import aiohttp
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.custom_emojis import telegram_api_semaphore
from app.core.config import settings
from app.models.tic_tac_toe import TicTacToeGame

logger = logging.getLogger(__name__)

HTML = """<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>
*{box-sizing:border-box}body{margin:0;background:transparent;color:var(--tg-theme-text-color,#eef4ff);font:14px system-ui,sans-serif}
.card{padding:16px;border-radius:22px;background:linear-gradient(150deg,var(--tg-theme-secondary-bg-color,#19283d),var(--tg-theme-bg-color,#111a2c));border:1px solid var(--tg-theme-button-color,#438df4)}
.top{display:flex;justify-content:space-between;align-items:center;color:var(--tg-theme-hint-color,#aabbd1);font-size:11px;font-weight:800;letter-spacing:.5px}
h1{font-size:21px;margin:8px 0 2px}.sub{font-size:12px;color:var(--tg-theme-hint-color,#aabbd1);margin:0 0 12px}
.status{min-height:29px;padding:7px 10px;border-radius:12px;background:var(--tg-theme-button-color,#317ff2);color:var(--tg-theme-button-text-color,#fff);font-size:12px;font-weight:750;text-align:center}
.board{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:13px 0}.cell{height:64px;border:1px solid var(--tg-theme-button-color,#438df4);border-radius:15px;background:var(--tg-theme-bg-color,#102039);color:var(--tg-theme-text-color,#fff);font-size:38px;font-weight:850;text-align:center;line-height:60px}
.cell.x{color:#61b1ff}.cell.o{color:#ffbd75}.cell:active{background:var(--tg-theme-button-color,#317ff2)}.foot{display:flex;justify-content:space-between;color:var(--tg-theme-hint-color,#aabbd1);font-size:11px}.clock{font-weight:900;color:#ffb86c}
</style></head><body><main class="card"><div class="top"><span>GOD OF DARS · GAME</span><span>۰۱ / دوز</span></div><h1>✕  دوز  ◯</h1><p class="sub" id="mode">بازی دوستانه</p><div class="status" id="status">در حال بارگذاری...</div><div class="board" id="board"></div><div class="foot"><span>هر حرکت: ۶۰ ثانیه</span><span class="clock" id="clock"></span></div></main><script>
var state={},busy=false;function read(raw){try{return JSON.parse(raw||'{}')}catch(e){return {}}}
function draw(){var b=document.getElementById('board');b.innerHTML='';var v=TelegramWidget.viewer;var me=v&&v.id;var active=state.status==='active';for(var i=0;i<9;i++){var cell=document.createElement('button');cell.className='cell '+(state.board&&state.board[i]==='X'?'x':state.board&&state.board[i]==='O'?'o':'');cell.textContent=state.board&&state.board[i]!=='.'?state.board[i]:'';cell.disabled=!active||busy||state.turn!==me||cell.textContent!=='';cell.setAttribute('data-i',String(i));b.appendChild(cell)}document.getElementById('mode').textContent=state.mode==='wager'?'شرط: '+state.stake+' '+(state.currency==='coin'?'طلا':'الماس'):state.mode==='computer'?'بازی با ربات':'بازی دوستانه';var label='';if(active)label=state.turn===me?'نوبت توئه · یه خونه رو انتخاب کن':'نوبت حریفه';else if(state.status==='cancelled')label='بازی لغو شد';else if(state.winner===null)label='بازی مساوی شد';else label=state.winner===me?'بردی! 🎉':'باختی!';document.getElementById('status').textContent=label;tick()}
function tick(){var el=document.getElementById('clock');if(state.status!=='active'){el.textContent='';return}var left=Math.max(0,Math.ceil((state.deadline*1000-Date.now())/1000));el.textContent=left+' ثانیه'}
document.getElementById('board').addEventListener('click',function(e){var i=e.target.getAttribute('data-i');if(i===null||busy)return;busy=true;draw();TelegramWidget.request('move:'+state.id+':'+i).then(function(a){var next=read(a.result);busy=false;if(next.error){draw();document.getElementById('status').textContent=next.error}else if(next.board){state=next;draw()}else draw()},function(){busy=false;draw();document.getElementById('status').textContent='ارتباط برقرار نشد؛ دوباره تلاش کن'})});state=read(TelegramWidget.publicData);TelegramWidget.onEvent('publicDataChanged',function(){state=read(TelegramWidget.publicData);busy=false;draw()});draw();setInterval(tick,1000);</script></body></html>"""

assert len(HTML.encode()) <= 32768 and len(zlib.compress(HTML.encode(), 9)) <= 4096


def state_json(
    game: TicTacToeGame, challenger_telegram_id: int, opponent_telegram_id: int | None
) -> str:
    return json.dumps(
        {
            "id": game.id,
            "board": game.board,
            "last_move": game.last_move,
            "status": game.status,
            "turn": challenger_telegram_id
            if game.turn_id == game.challenger_id
            else opponent_telegram_id
            if game.turn_id == game.opponent_id
            else None,
            "winner": challenger_telegram_id
            if game.winner_id == game.challenger_id
            else opponent_telegram_id
            if game.winner_id == game.opponent_id
            else 0
            if game.winner_id == -1
            else None,
            "deadline": int(game.deadline_at.astimezone(UTC).timestamp())
            if game.deadline_at
            else 0,
            "mode": game.mode,
            "variant": game.variant,
            "challenger": challenger_telegram_id,
            "currency": game.stake_type,
            "stake": game.stake_amount,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def fallback_text(game: TicTacToeGame, player_id: int) -> str:
    board = ["❌" if c == "X" else "⭕" if c == "O" else "▫️" for c in game.board]
    grid = "\n".join("  ".join(board[i : i + 3]) for i in (0, 3, 6))
    if game.status == "active":
        status = (
            "نوبت توئه؛ ۶۰ ثانیه وقت داری."
            if game.turn_id == player_id
            else "نوبت حریفه."
        )
    elif game.status == "cancelled":
        status = "بازی لغو شد."
    elif game.winner_id is None:
        status = "بازی مساوی شد."
    else:
        status = "برنده شدی 🎉" if game.winner_id == player_id else "باختی."
    stake = (
        f"\nشرط: {game.stake_amount:,} {'طلا' if game.stake_type == 'coin' else 'الماس'}"
        if game.mode == "wager"
        else ""
    )
    return f"🎮 دوز{stake}\n\n{grid}\n\n{status}"


def fallback_keyboard(
    game: TicTacToeGame, player_id: int
) -> InlineKeyboardMarkup | None:
    if game.status != "active":
        return None
    cells = []
    for i, c in enumerate(game.board):
        label = "❌" if c == "X" else "⭕" if c == "O" else "·"
        cells.append(
            InlineKeyboardButton(
                text=label,
                callback_data=f"ttt:move:{game.id}:{i}"
                if c == "." and game.turn_id == player_id
                else "ttt:noop",
            )
        )
    return InlineKeyboardMarkup(inline_keyboard=[cells[i : i + 3] for i in (0, 3, 6)])


async def widget_api(
    bot: Any, method: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    session = await bot.session.create_session()
    url = bot.session.api.api_url(token=bot.token, method=method)
    timeout = aiohttp.ClientTimeout(total=settings.TELEGRAM_REQUEST_TIMEOUT_SECONDS)
    for attempt in range(settings.TELEGRAM_RETRY_AFTER_MAX + 1):
        try:
            async with (
                telegram_api_semaphore(),
                session.post(url, json=payload, timeout=timeout) as response,
            ):
                result = await response.json(content_type=None)
            if result.get("ok"):
                return result
            if response.status == 429 and attempt < settings.TELEGRAM_RETRY_AFTER_MAX:
                retry_after = result.get("parameters", {}).get("retry_after", 1)
                if 0 <= retry_after <= settings.TELEGRAM_MAX_RETRY_DELAY_SECONDS:
                    await asyncio.sleep(retry_after)
                    continue
            logger.warning("Widget %s failed: %s", method, result.get("description"))
            return None
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError):
            logger.exception("Widget %s request failed", method)
            return None
    return None
