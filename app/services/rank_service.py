"""Monthly ranked cups, tier-first matchmaking, and attack rewards."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.attack import Attack
from app.models.castle import Castle
from app.models.rank_profile import RankProfile
from app.models.resource import Resource
from app.models.user import User
from app.models.user_shield import UserShield
from app.services.notification_service import NotificationService
from app.services.resource_service import ResourceService
from app.services.school_errors import RandomOpponentNotFound, RankDailyLimitReached


@dataclass(frozen=True)
class Tier:
    minimum: int
    name: str
    icon: str
    emoji_id: str
    coin: int
    banana: int
    diamond: int


# Rewards are paid once per completed ranked command and at monthly rollover.
TIERS = (
    Tier(0, "مبتدی", "📚", "5918211539407478280", 0, 0, 0),
    Tier(201, "برنزی", "🦁", "5915973075467247683", 20, 0, 0),
    Tier(601, "نقره‌ای", "💋", "5915876954099167273", 50, 2, 0),
    Tier(1001, "طلایی", "💀", "5918257843449896869", 90, 4, 0),
    Tier(1401, "سوپر طلایی", "✋", "5915795444209820476", 140, 6, 2),
    Tier(1801, "دیاموندی", "🤓", "5915508067948051685", 200, 8, 4),
    Tier(2201, "پلاتینیومی", "🙏", "5918003894918586239", 280, 12, 7),
    Tier(2601, "فرمانده", "🤩", "5915888842568638290", 400, 18, 12),
)
DAILY_LIMIT = 20
RANK_TIMEZONE = ZoneInfo("Asia/Tehran")


def tier_for(cups: int) -> Tier:
    return next(tier for tier in reversed(TIERS) if cups >= tier.minimum)


def match_tier_order(own_index: int) -> tuple[int, ...]:
    """Search own tier, every higher tier, then lower tiers from nearest down."""
    return tuple(range(own_index, len(TIERS))) + tuple(range(own_index - 1, -1, -1))


def season_start(now: datetime | None = None) -> datetime:
    current = (now or datetime.now(UTC)).astimezone(RANK_TIMEZONE)
    return current.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(
        UTC
    )


def local_date(now: datetime | None = None):
    return (now or datetime.now(UTC)).astimezone(RANK_TIMEZONE).date()


@dataclass(frozen=True)
class RankView:
    cups: int
    tier: Tier
    wins: int
    losses: int
    attacks_left: int
    next_cups: int | None


@dataclass(frozen=True)
class RankSettlement:
    delta: tuple[int, int]
    reward: tuple[int, int, int]


class RankService:
    @staticmethod
    async def view(
        session: AsyncSession, user_id: int, *, now: datetime | None = None
    ) -> RankView:
        now = now or datetime.now(UTC)
        profile = await session.get(RankProfile, user_id)
        current = (
            profile
            if profile is not None and profile.season_start == season_start(now)
            else None
        )
        cups = current.cups if current is not None else 0
        tier = tier_for(cups)
        next_cups = next((item.minimum for item in TIERS if item.minimum > cups), None)
        daily = (
            current.daily_attacks
            if current is not None and current.daily_date == local_date(now)
            else 0
        )
        return RankView(
            cups,
            tier,
            current.wins if current is not None else 0,
            current.losses if current is not None else 0,
            DAILY_LIMIT - daily,
            next_cups,
        )

    @staticmethod
    async def locked_profile(
        session: AsyncSession, user: User, *, now: datetime | None = None
    ) -> RankProfile:
        """Caller locks the user first, preserving the attack lock order."""
        now = now or datetime.now(UTC)
        profile = await session.scalar(
            select(RankProfile).where(RankProfile.user_id == user.id).with_for_update()
        )
        if profile is None:
            profile = RankProfile(user_id=user.id, season_start=season_start(now))
            session.add(profile)
            await session.flush()
        elif profile.season_start != season_start(now):
            await RankService._rollover(session, user, profile, now=now)
        return profile

    @staticmethod
    async def _rollover(
        session: AsyncSession, user: User, profile: RankProfile, *, now: datetime
    ) -> None:
        old_start = profile.season_start
        old_tier = tier_for(profile.cups)
        # The row lock and new season key make this payout idempotent across workers.
        if profile.wins or profile.losses:
            ref = int(old_start.timestamp())
            if old_tier.coin:
                await ResourceService.credit_coin(
                    session,
                    user.resources,
                    user_id=user.id,
                    amount=old_tier.coin,
                    reason="RANK_SEASON_REWARD",
                    reference_type="RANK_SEASON",
                    reference_id=ref,
                )
            if old_tier.banana:
                await ResourceService.credit_banana(
                    session,
                    user.resources,
                    user_id=user.id,
                    amount=old_tier.banana,
                    reason="RANK_SEASON_REWARD",
                    reference_type="RANK_SEASON",
                    reference_id=ref,
                )
            if old_tier.diamond:
                await ResourceService.credit_diamond(
                    session,
                    user.resources,
                    user_id=user.id,
                    amount=old_tier.diamond,
                    reason="RANK_SEASON_REWARD",
                    reference_type="RANK_SEASON",
                    reference_id=ref,
                )
            from app.bot.banners import MARKDOWN_V2
            from app.bot.rank_banners import rank_season_reward_banner

            await NotificationService().enqueue(
                session,
                notification_type="RANK_SEASON_REWARD",
                recipient_user_id=user.id,
                idempotency_key=f"RANK_SEASON_REWARD:{ref}:{user.id}",
                payload={
                    "chat_id": user.telegram_user_id,
                    "parse_mode": MARKDOWN_V2,
                    "text": rank_season_reward_banner(old_tier, profile.cups),
                },
            )
        profile.season_start = season_start(now)
        profile.cups = profile.best_cups = profile.wins = profile.losses = 0
        profile.daily_date = local_date(now)
        profile.daily_attacks = 0

    @staticmethod
    async def reserve_attack(
        session: AsyncSession, user: User, *, now: datetime | None = None
    ) -> None:
        now = now or datetime.now(UTC)
        profile = await RankService.locked_profile(session, user, now=now)
        today = local_date(now)
        if profile.daily_date != today:
            profile.daily_date = today
            profile.daily_attacks = 0
        if profile.daily_attacks >= DAILY_LIMIT:
            raise RankDailyLimitReached
        profile.daily_attacks += 1

    @staticmethod
    async def assert_available(session: AsyncSession, user_id: int) -> None:
        if (await RankService.view(session, user_id)).attacks_left <= 0:
            raise RankDailyLimitReached

    @staticmethod
    async def match(
        session: AsyncSession,
        attacker: User,
        *,
        excluded: set[int],
        recent: tuple[int, ...],
    ) -> User:
        now = datetime.now(UTC)
        current_season = season_start(now)
        attacker_profile = await session.get(RankProfile, attacker.id)
        cups = (
            attacker_profile.cups
            if attacker_profile and attacker_profile.season_start == current_season
            else 0
        )
        effective_cups = case(
            (RankProfile.season_start == current_season, RankProfile.cups), else_=0
        )
        tier_index = case(
            *[
                (effective_cups >= item.minimum, i)
                for i, item in reversed(list(enumerate(TIERS)))
            ],
            else_=0,
        )
        own_index = TIERS.index(tier_for(cups))
        active_shield = (
            select(UserShield.id)
            .where(
                UserShield.user_id == User.id,
                UserShield.active_until.is_not(None),
                UserShield.active_until > now,
            )
            .exists()
        )
        base = (
            select(User)
            .outerjoin(RankProfile, RankProfile.user_id == User.id)
            .options(selectinload(User.resources))
            .where(
                User.is_active.is_(True),
                User.telegram_user_id > 0,
                User.id != attacker.id,
                or_(User.free_shield_until.is_(None), User.free_shield_until <= now),
                ~active_shield,
                select(Castle.id).where(Castle.user_id == User.id).exists(),
                select(Resource.id).where(Resource.user_id == User.id).exists(),
            )
            .order_by(
                func.abs(effective_cups - cups),
                func.abs(User.level - attacker.level),
                func.random(),
            )
            .limit(1)
        )
        for candidate_tier in match_tier_order(own_index):
            for exclusions in (excluded | set(recent), excluded):
                target = await session.scalar(
                    base.where(
                        tier_index == candidate_tier,
                        User.id.not_in(exclusions),
                    )
                )
                if target is not None:
                    return target
        raise RandomOpponentNotFound

    @staticmethod
    async def settle_command(
        session: AsyncSession, attacks: list[Attack], attacker: User, target: User
    ) -> RankSettlement | None:
        first = attacks[0]
        if not first.is_ranked or first.rank_settled:
            return None
        now = datetime.now(UTC)
        attacker_rank = await RankService.locked_profile(session, attacker, now=now)
        defender_rank = await RankService.locked_profile(session, target, now=now)
        tier = tier_for(attacker_rank.cups)
        reward = (tier.coin, tier.banana, tier.diamond)
        for amount, credit in (
            (tier.coin, ResourceService.credit_coin),
            (tier.banana, ResourceService.credit_banana),
            (tier.diamond, ResourceService.credit_diamond),
        ):
            if amount:
                await credit(
                    session,
                    None,
                    user_id=attacker.id,
                    amount=amount,
                    reason="RANK_ATTACK_REWARD",
                    reference_type="RANK_ATTACK",
                    reference_id=first.id,
                )
        successful = any(row.is_successful for row in attacks)
        gap = defender_rank.cups - attacker_rank.cups
        if successful:
            gain = max(12, min(40, 25 + gap // 80))
            loss = max(6, min(22, 12 - gap // 160))
            attacker_rank.cups += gain
            attacker_rank.best_cups = max(attacker_rank.best_cups, attacker_rank.cups)
            attacker_rank.wins += 1
            actual_loss = min(defender_rank.cups, loss)
            defender_rank.cups -= actual_loss
            defender_rank.losses += 1
            delta = (gain, -actual_loss)
        else:
            penalty = min(attacker_rank.cups, 8)
            attacker_rank.cups -= penalty
            attacker_rank.losses += 1
            delta = (-penalty, 0)
        first.rank_settled = True
        return RankSettlement(delta, reward)


async def settle_expired_seasons(*, batch_size: int = 100) -> int:
    """Background sweep pays offline players and resets their monthly state."""
    from app.db.session import AsyncSessionLocal

    current = season_start()
    async with AsyncSessionLocal() as session:
        ids = list(
            await session.scalars(
                select(RankProfile.user_id)
                .where(RankProfile.season_start < current)
                .order_by(RankProfile.user_id)
                .limit(batch_size)
            )
        )
        await session.rollback()
        for user_id in ids:
            async with session.begin():
                user = await session.scalar(
                    select(User)
                    .where(User.id == user_id)
                    .options(selectinload(User.resources))
                    .with_for_update()
                )
                if user is not None:
                    await RankService.locked_profile(session, user)
        return len(ids)
