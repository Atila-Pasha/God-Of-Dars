"""Telegram MarkdownV2 banners for the monthly ranked league."""

from __future__ import annotations

from app.bot.banners import bold, emoji, escape
from app.services.rank_service import DAILY_LIMIT, TIERS, RankView, Tier

TROPHY = emoji("5823430604846276719", "🏆")
BATTLE = emoji("5825697157872623308", "⚔️")
REWARD = emoji("5825832256068918886", "🎁")
COIN = emoji("5825656871079387950", "🪙")
BANANA = emoji("5825496299432058457", "🍌")
DIAMOND = emoji("5825753314570018832", "💎")
CLOCK = emoji("6039539366177541657", "⏰")
EMOJI_GAP = "\u2002\u2002"


def _tier_icon(tier: Tier) -> str:
    return emoji(tier.emoji_id, tier.icon)


def _reward(tier: Tier) -> str:
    if not (tier.coin or tier.banana or tier.diamond):
        return escape("بدون پاداش")
    parts = []
    if tier.coin:
        parts.append(f"{COIN}{EMOJI_GAP}{escape(f'{tier.coin} طلا')}")
    if tier.banana:
        parts.append(f"{BANANA}{EMOJI_GAP}{escape(f'{tier.banana} موز')}")
    if tier.diamond:
        parts.append(f"{DIAMOND}{EMOJI_GAP}{escape(f'{tier.diamond} الماس')}")
    return escape("  ·  ").join(parts)


def _range(index: int) -> str:
    tier = TIERS[index]
    if index == len(TIERS) - 1:
        return escape(f"{tier.minimum}+ جام")
    return escape(f"{tier.minimum}–{TIERS[index + 1].minimum - 1} جام")


def _status(view: RankView) -> str:
    next_tier = next((tier for tier in TIERS if tier.minimum == view.next_cups), None)
    progress = (
        f"تا {next_tier.name}: {view.next_cups - view.cups} جام"
        if view.next_cups is not None and next_tier is not None
        else "به بالاترین رنک رسیده‌ای!"
    )
    return (
        f"{TROPHY} {bold('تالار رنک | فصل ماهانه')}\n\n"
        f"{_tier_icon(view.tier)} {bold(view.tier.name)}  {escape('•')}  "
        f"{bold(f'{view.cups} جام')}\n"
        f"> {escape(progress)}\n\n"
        f"{BATTLE} {bold('کارنامهٔ این فصل')}\n"
        f"> {escape(f'برد {view.wins}  |  باخت {view.losses}')}\n"
        f"> {escape(f'فرصت حملهٔ امروز {view.attacks_left} / {DAILY_LIMIT}')}"
    )


def rank_status_banner(view: RankView) -> str:
    """Full rank card with every tier and its end-of-season prize."""
    rows = [
        f"{_tier_icon(tier)} {bold(tier.name)}  {escape('•')}  {_range(index)}\n"
        f">  {_reward(tier)}"
        for index, tier in enumerate(TIERS)
    ]
    return (
        f"{_status(view)}\n\n"
        f"{REWARD} {bold('پاداش هر حملهٔ رنکی')}\n"
        + "\n".join(rows)
        + "\n\n"
        + f"{CLOCK} {escape('ریست: روز اول هر ماه میلادی، ساعت 00:00 تهران')}\n"
        + escape(
            "پاداش حمله براساس رنک هنگام نبرد است. پایان ماه هم پاداش رنک پایانی پرداخت می‌شود و فصل تازه با 0 جام آغاز می‌شود."
        )
    )


def rank_profile_banner(view: RankView) -> str:
    """Compact card for the profile section."""
    return (
        f"{_status(view)}\n\n"
        f"{REWARD} {bold('پاداش هر حمله در این رنک')}\n"
        f">  {_reward(view.tier)}\n\n"
        f"{CLOCK} {escape('ریست: روز اول هر ماه میلادی، ساعت 00:00 تهران')}\n"
        + escape("برای دیدن جدول کامل رنک‌ها و جوایز، /rank را بفرست.")
    )


def rank_season_reward_banner(tier: Tier, cups: int) -> str:
    return (
        f"{TROPHY} {bold('فصل رنک به پایان رسید!')}\n\n"
        f"{_tier_icon(tier)} {bold(tier.name)}  {escape('•')}  "
        f"{bold(f'{cups} جام')}\n\n"
        f"{REWARD} {bold('پاداش فصل')}\n"
        f">  {_reward(tier)}\n\n"
        + escape("فصل تازه با 0 جام آغاز شد. برای دیدن مسیر جدید، /rank را بفرست.")
    )
