"""Telegram widget-sandbox leaderboard cards (Bot API 10.4 beta)."""

from __future__ import annotations

import logging
import zlib
from base64 import b64encode
from datetime import datetime
from html import escape
from importlib.resources import files
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
from aiogram.types import InlineKeyboardMarkup, ReplyParameters

from app.core.config import settings
from app.services.leaderboard_service import (
    FighterPage,
    LeaderboardEntry,
    LeaderboardKind,
    LeaderboardPeriod,
)
from app.services.rank_service import TIERS, tier_for

logger = logging.getLogger(__name__)
_TIER_SPRITE = b64encode(
    files("app.services").joinpath("assets/rank-emoji-sprite.webp").read_bytes()
).decode("ascii")

_STYLE = """<style>
*{box-sizing:border-box}body{margin:0;padding:0;font:14px system-ui,sans-serif;color:var(--tg-theme-text-color,#ecf3ff);direction:rtl}
.card{padding:12px;border-radius:22px;background:linear-gradient(145deg,var(--tg-theme-secondary-bg-color,#17243a),var(--tg-theme-bg-color,#111b2e));border:1px solid rgba(140,170,235,.25);box-shadow:0 12px 32px rgba(0,0,0,.14)}
.top{display:flex;align-items:center;justify-content:space-between;gap:10px}.kicker{font-size:10px;font-weight:800;letter-spacing:1px;color:var(--tg-theme-accent-text-color,#76b9ff)}
.period{font-size:11px;font-weight:700;padding:5px 9px;border-radius:99px;color:var(--tg-theme-button-text-color,#fff);background:var(--tg-theme-button-color,#3d82e4)}
h1{font-size:18px;line-height:1.3;margin:6px 0 2px}p{margin:0}.sub{font-size:11px;color:var(--tg-theme-hint-color,#9caec8)}
.champ{margin:8px 0;padding:7px 10px;border-radius:14px;background:linear-gradient(100deg,rgba(255,190,65,.24),rgba(255,190,65,.04));border:1px solid rgba(255,196,79,.35)}
.champ small{display:block;font-size:10px;color:var(--tg-theme-hint-color,#b4bdd1)}.champ strong{display:block;margin-top:2px;font-size:15px}
.head,.row{display:grid;grid-template-columns:42px minmax(0,1fr) 68px 54px;align-items:center;gap:4px}.head{padding:4px 5px;font-size:10px;color:var(--tg-theme-hint-color,#9caec8)}
.row{min-height:27px;padding:1px 5px;border-top:1px solid rgba(140,170,235,.13);font-size:12px}.row:nth-child(even){background:rgba(130,165,235,.05)}
.rank{font-weight:800}.name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:650}.metric{text-align:center;font-variant-numeric:tabular-nums;font-weight:800}.minor{text-align:center;font-size:11px;color:var(--tg-theme-hint-color,#aab9d3)}
.me{margin-top:6px;padding:6px 10px;border-radius:13px;border:1px solid var(--tg-theme-button-color,#3d82e4);background:rgba(85,143,244,.11)}
.me small{display:block;color:var(--tg-theme-hint-color,#aab9d3);font-size:10px}.me strong{display:block;margin-top:2px;font-size:13px}.foot{margin-top:4px;color:var(--tg-theme-hint-color,#aab9d3);font-size:10px}
.tier{display:inline-block;width:24px;height:24px;vertical-align:middle;background-size:192px 24px;background-repeat:no-repeat}.updated{margin-top:4px;font-size:10px;color:var(--tg-theme-hint-color,#aab9d3)}
</style>"""
_STYLE = _STYLE.replace(
    "</style>",
    f".tier{{background-image:url(data:image/webp;base64,{_TIER_SPRITE})}}"
    + "".join(
        f".t{index}{{background-position:-{index * 24}px 0}}"
        for index in range(len(TIERS))
    )
    + "</style>",
)


def _text(value: str) -> str:
    return escape(value, quote=False)


def _name(entry: LeaderboardEntry) -> str:
    value = f"@{entry.username}" if entry.username else entry.name
    value = " ".join(value.split())
    rendered = _text(value[:24] + ("…" if len(value) > 24 else ""))
    return f'<bdi dir="ltr">{rendered}</bdi>' if entry.username else rendered


def _number(value: int) -> str:
    return f"{value:,}"


def _updated_at(value: datetime | None) -> str:
    if value is None:
        return ""
    local = value.astimezone(ZoneInfo(settings.LEADERBOARD_TIMEZONE))
    return (
        f'<p class="updated">آخرین به‌روزرسانی: {local:%Y/%m/%d، %H:%M} · هر ۱ ساعت</p>'
    )


def _tier_icon(cups: int) -> str:
    tier = tier_for(cups)
    return f'<span class="tier t{TIERS.index(tier)}" title="{tier.name}"></span>'


def _row(entry: LeaderboardEntry, secondary: str) -> str:
    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(entry.rank, f"{entry.rank:02d}")
    return (
        '<div class="row">'
        f'<span class="rank">{medal}</span>'
        f'<span class="name">{_name(entry)}</span>'
        f'<span class="metric">{_number(entry.primary_value)}</span>'
        f'<span class="minor">{secondary}</span>'
        "</div>"
    )


def _shell(title: str, period: str, sub: str, body: str) -> str:
    return (
        '<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
        + _STYLE
        + '</head><body><main class="card">'
        + '<div class="top"><span class="kicker">GOD OF DARS / LEADERBOARD</span>'
        + f'<span class="period">{period}</span></div>'
        + f'<h1>{title}</h1><p class="sub">{sub}</p>'
        + body
        + "</main></body></html>"
    )


def leaderboard_widget_html(
    kind: LeaderboardKind,
    entries: tuple[LeaderboardEntry, ...],
    viewer: LeaderboardEntry | None,
    period: LeaderboardPeriod,
    updated_at: datetime | None = None,
) -> str:
    titles = {
        "commander": "👑 برترین فرمانده‌ها",
        "student": "📚 برترین دانش‌آموزها",
        "fighter": "⚔️ برترین مبارزها",
    }
    periods = {"daily": "امروز", "weekly": "این هفته", "monthly": "این ماه"}
    headers = {
        "commander": ("امتیاز", "سطح"),
        "student": ("صحیح", "دقت"),
        "fighter": ("جام", "برد"),
    }
    period = "monthly" if kind == "fighter" else period
    primary, secondary = headers[kind]
    body = ""
    if entries and entries[0].rank == 1:
        champion = entries[0]
        body += f'<div class="champ"><small>✦ صدرنشین میدان</small><strong>{_name(champion)} · {_number(champion.primary_value)} {primary}</strong></div>'
    body += f'<div class="head"><span>رتبه</span><span>نام</span><span>{primary}</span><span>{secondary}</span></div>'
    for entry in entries:
        if kind == "student":
            value = (
                round(entry.primary_value / entry.secondary_value * 100)
                if entry.secondary_value
                else 0
            )
            detail = f"{value}٪"
        else:
            detail = _number(entry.secondary_value)
        body += _row(entry, detail)
    if not entries:
        body += '<div class="row">هنوز رکوردی ثبت نشده است.</div>'
    if viewer is None:
        body += '<div class="me"><small>جایگاه تو</small><strong>هنوز در جدول نیستی · وقت شروع است ✨</strong></div>'
    else:
        body += f'<div class="me"><small>جایگاه تو</small><strong>#{viewer.rank} · {_name(viewer)} · {_number(viewer.primary_value)} {primary}</strong></div>'
    body += _updated_at(updated_at)
    body += '<p class="foot">داده‌های جدول هر ساعت به‌روزرسانی می‌شوند.</p>'
    return _shell(titles[kind], periods[period], "بهترین‌ها در یک نگاه", body)


def global_rank_widget_html(page: FighterPage, viewer: LeaderboardEntry | None) -> str:
    body = f'<p class="sub">👥 {_number(page.total)} مبارز · صفحه {page.page}/{page.pages}</p>'
    if page.page == 1 and page.entries:
        champion = page.entries[0]
        body += f'<div class="champ"><small>✦ قهرمان فصل</small><strong>{_name(champion)} · {_number(champion.primary_value)} جام</strong></div>'
    body += '<div class="head"><span>رتبه</span><span>مبارز</span><span>جام</span><span>رنک</span></div>'
    for entry in page.entries:
        body += _row(entry, _tier_icon(entry.primary_value))
    if not page.entries:
        body += '<div class="row">هنوز مبارزی وارد رنک نشده است.</div>'
    if viewer is None:
        body += '<div class="me"><small>جایگاه تو</small><strong>هنوز وارد رنک فصل نشده‌ای</strong></div>'
    else:
        tier = tier_for(viewer.primary_value)
        next_tier = next(
            (item for item in TIERS if item.minimum > viewer.primary_value), None
        )
        progress = (
            f"{_number(next_tier.minimum - viewer.primary_value)} جام تا {next_tier.name}"
            if next_tier
            else "به بالاترین رنک رسیده‌ای!"
        )
        body += f'<div class="me"><small>جایگاه تو · {_tier_icon(viewer.primary_value)} {tier.name}</small><strong>#{viewer.rank} · {_number(viewer.primary_value)} جام</strong><small>{progress}</small></div>'
    body += _updated_at(page.updated_at)
    body += '<p class="foot">جام بیشتر، جایگاه بالاتر · به‌روزرسانی هر ساعت</p>'
    return _shell("🏆 تالار مبارزان سراسری", "فصل ماهانه", "نبرد برای تاج رنک", body)


def validate_widget_size(html: str) -> None:
    source = html.encode("utf-8")
    if len(source) > 32_768 or len(zlib.compress(source, 9)) > 4_096:
        raise ValueError("leaderboard widget exceeds Telegram's size limits")


async def send_leaderboard_widget(
    bot: Any,
    chat_id: int,
    html: str,
    *,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    reply_parameters: ReplyParameters | None = None,
) -> bool:
    """Send through Bot API 10.4 beta; return False for unsupported endpoints."""
    if not settings.TELEGRAM_WIDGET_BETA_ENABLED:
        return False
    try:
        validate_widget_size(html)
    except ValueError:
        logger.warning("Telegram widget exceeded size limit; using text fallback")
        return False
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "html": html,
        "caption": caption,
        "width": 0,
        "height": 0,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup.model_dump(exclude_none=True)
    if reply_parameters is not None:
        payload["reply_parameters"] = reply_parameters.model_dump(exclude_none=True)
    api_base = settings.TELEGRAM_WIDGET_API_BASE.rstrip("/")
    url = f"{api_base}/bot{bot.token}/sendWidget"
    timeout = aiohttp.ClientTimeout(total=settings.TELEGRAM_REQUEST_TIMEOUT_SECONDS)
    try:
        session = await bot.session.create_session()
        async with session.post(url, json=payload, timeout=timeout) as response:
            result = await response.json(content_type=None)
        if result.get("ok") is True:
            return True
        logger.warning(
            "Telegram widget unavailable: %s",
            result.get("description", "unknown error"),
        )
    except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
        logger.warning("Telegram widget request failed: %s", type(exc).__name__)
    return False
