from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.castle import Castle
from app.models.defense import Defense
from app.models.rank_profile import RankProfile
from app.models.resource import Resource
from app.models.teacher import Teacher
from app.models.transaction import Transaction
from app.models.user import User
from app.models.user_teacher import UserTeacher
from app.repositories.leaderboard import LeaderboardRepository
from app.services.attack_service import AttackService
from app.services.leaderboard_service import LeaderboardService
from app.services.rank_service import RankService, local_date, season_start
from app.services.school_errors import RandomOpponentNotFound, RankDailyLimitReached
from app.workers.attack_resolver import _command_result


@pytest.mark.asyncio
async def test_global_rank_pages_include_zero_battle_players() -> None:
    async with AsyncSessionLocal() as session:
        transaction = await session.begin()
        try:
            player_ids = []
            for index in range(12):
                player = User(
                    telegram_user_id=uuid4().int % 2_000_000_000,
                    first_name=f"rank-page-{index}",
                )
                session.add(player)
                await session.flush()
                player_ids.append(player.id)
                session.add(
                    RankProfile(
                        user_id=player.id,
                        season_start=season_start(),
                        cups=1_000_012 - index,
                        best_cups=1_000_012 - index,
                    )
                )
            await session.flush()

            service = LeaderboardService()
            first = await service.fighter_page(session, 1)
            second = await service.fighter_page(session, 2)

            assert [entry.user_id for entry in first.entries] == player_ids[:10]
            assert [entry.user_id for entry in second.entries[:2]] == player_ids[10:]
            assert [entry.rank for entry in second.entries[:2]] == [11, 12]
        finally:
            await transaction.rollback()


@pytest.mark.asyncio
async def test_ranked_match_daily_limit_and_monthly_rewards_in_database() -> None:
    async with AsyncSessionLocal() as session:
        transaction = await session.begin()
        try:
            now = datetime.now(UTC)
            current = season_start(now)
            existing_ids = set(await session.scalars(select(User.id)))

            # Very high cups isolate the candidates from real development users.
            def player(name: str, *, protected: bool = False) -> User:
                user = User(
                    telegram_user_id=uuid4().int % 2_000_000_000,
                    first_name=name,
                    level=3,
                    free_shield_until=now + timedelta(hours=1) if protected else None,
                )
                user.resources = Resource(coin=10, banana=0, diamond=0)
                user.castle = Castle(strength=100, defense=Defense(defense_power=20))
                return user

            attacker = player("attacker")
            near = player("near")
            far = player("far")
            shielded = player("shielded", protected=True)
            mismatched = player("mismatched")
            session.add_all((attacker, near, far, shielded, mismatched))
            await session.flush()
            for user, cups in (
                (attacker, 900_000),
                (near, 900_040),
                (far, 900_220),
                (shielded, 900_010),
                (mismatched, 900_500),
            ):
                session.add(
                    RankProfile(
                        user_id=user.id,
                        season_start=current,
                        cups=cups,
                        best_cups=cups,
                        wins=1,
                        daily_date=local_date(now),
                    )
                )
            await session.flush()

            leaders = await LeaderboardRepository().fighters(
                session, limit=5, since=current
            )
            assert [item.user_id for item in leaders] == [
                mismatched.id,
                far.id,
                near.id,
                shielded.id,
                attacker.id,
            ]

            target = await RankService.match(
                session, attacker, excluded=existing_ids, recent=()
            )
            assert target.id == near.id
            target = await RankService.match(
                session, attacker, excluded=existing_ids | {near.id}, recent=()
            )
            assert target.id == far.id
            with pytest.raises(RandomOpponentNotFound):
                await RankService.match(
                    session,
                    attacker,
                    excluded=existing_ids
                    | {near.id, far.id, shielded.id, mismatched.id},
                    recent=(),
                )

            attack = SimpleNamespace(
                id=8_000_001,
                is_ranked=True,
                rank_settled=False,
                is_successful=True,
            )
            settlement = await RankService.settle_command(
                session, [attack], attacker, near
            )
            assert settlement is not None
            assert settlement.reward == (400, 18, 12)
            assert attacker.resources.coin == 410
            attack_rewards = list(
                await session.scalars(
                    select(Transaction).where(
                        Transaction.user_id == attacker.id,
                        Transaction.reason == "RANK_ATTACK_REWARD",
                    )
                )
            )
            assert sorted(row.amount for row in attack_rewards) == [12, 18, 400]
            assert (
                await RankService.settle_command(session, [attack], attacker, near)
                is None
            )

            profile = await RankService.locked_profile(session, attacker, now=now)
            profile.daily_attacks = 19
            await RankService.reserve_attack(session, attacker, now=now)
            with pytest.raises(RankDailyLimitReached):
                await RankService.reserve_attack(session, attacker, now=now)
            assert profile.daily_attacks == 20

            old = await RankService.locked_profile(session, near, now=now)
            old.season_start = season_start(current - timedelta(days=1))
            old.cups = 2201
            old.wins = 5
            before = near.resources.coin
            await RankService.locked_profile(session, near, now=now)
            await session.flush()
            assert old.cups == 0 and old.season_start == current
            assert near.resources.coin == before + 280
            rewards = list(
                await session.scalars(
                    select(Transaction).where(
                        Transaction.user_id == near.id,
                        Transaction.reason == "RANK_SEASON_REWARD",
                    )
                )
            )
            assert sorted(row.amount for row in rewards) == [7, 12, 280]
            await RankService.locked_profile(session, near, now=now)
            assert (
                len(
                    list(
                        await session.scalars(
                            select(Transaction).where(
                                Transaction.user_id == near.id,
                                Transaction.reason == "RANK_SEASON_REWARD",
                            )
                        )
                    )
                )
                == 3
            )
        finally:
            await transaction.rollback()


@pytest.mark.asyncio
async def test_real_opponent_can_launch_and_pay_one_ranked_attack() -> None:
    async with AsyncSessionLocal() as session:
        transaction = await session.begin()
        try:
            existing_ids = set(await session.scalars(select(User.id)))
            attacker = User(
                telegram_user_id=uuid4().int % 2_000_000_000,
                first_name="rank-attacker",
                level=3,
            )
            attacker.resources = Resource(coin=10, banana=0, diamond=0)
            attacker.castle = Castle(strength=100, defense=Defense(defense_power=0))
            opponent = User(
                telegram_user_id=uuid4().int % 2_000_000_000,
                first_name="rank-opponent",
                level=3,
            )
            opponent.resources = Resource(coin=10, banana=0, diamond=0)
            opponent.castle = Castle(strength=100, defense=Defense(defense_power=0))
            teacher = Teacher(
                name=f"rank-{uuid4().hex[:10]}",
                damage=100,
                max_hp=100,
                purchase_price=1,
                upgrade_price=1,
            )
            owned = UserTeacher(user=attacker, teacher=teacher, current_hp=100)
            session.add_all((attacker, opponent, owned))
            await session.flush()
            session.add(
                RankProfile(
                    user_id=attacker.id,
                    season_start=season_start(),
                    cups=201,
                    best_cups=201,
                )
            )
            session.add(
                RankProfile(
                    user_id=opponent.id,
                    season_start=season_start(),
                    cups=1001,
                    best_cups=1001,
                )
            )
            await session.flush()

            target = await RankService.match(
                session, attacker, excluded=existing_ids, recent=()
            )
            assert target.id == opponent.id
            service = AttackService()
            launch = await service.start_attack_by_ids(
                session,
                attacker_telegram_id=attacker.telegram_user_id,
                target_id=target.id,
                teacher_ids=[owned.id],
                ranked=True,
            )
            result = await service.resolve_pending_attack(session, launch.attack_ids[0])
            assert result is not None and result.attack.target_id == opponent.id
            summary = await _command_result(session, result)
            assert summary is not None
            assert summary.rank_reward == (20, 0, 0)
            rewards = list(
                await session.scalars(
                    select(Transaction).where(
                        Transaction.user_id == attacker.id,
                        Transaction.reason == "RANK_ATTACK_REWARD",
                    )
                )
            )
            assert len(rewards) == 1 and rewards[0].amount == 20
        finally:
            await transaction.rollback()


@pytest.mark.asyncio
async def test_same_tier_then_all_higher_then_lower_tiers() -> None:
    async with AsyncSessionLocal() as session:
        transaction = await session.begin()
        try:
            existing_ids = set(await session.scalars(select(User.id)))

            def player(name: str) -> User:
                user = User(
                    telegram_user_id=uuid4().int % 2_000_000_000,
                    first_name=name,
                    level=2,
                )
                user.resources = Resource(coin=0, banana=0, diamond=0)
                user.castle = Castle(strength=100, defense=Defense(defense_power=0))
                session.add(user)
                return user

            attacker = player("bronze-attacker")
            same = player("bronze-target")
            higher = player("silver-target")
            farther_higher = player("gold-target")
            lower = player("beginner-target")
            await session.flush()
            for user, cups in (
                (attacker, 600),
                (same, 201),
                (higher, 601),
                (farther_higher, 1001),
                (lower, 200),
            ):
                session.add(
                    RankProfile(
                        user_id=user.id,
                        season_start=season_start(),
                        cups=cups,
                    )
                )
            await session.flush()

            first = await RankService.match(
                session, attacker, excluded=existing_ids, recent=()
            )
            assert first.id == same.id
            second = await RankService.match(
                session,
                attacker,
                excluded=existing_ids | {same.id},
                recent=(),
            )
            assert second.id == higher.id
            third = await RankService.match(
                session,
                attacker,
                excluded=existing_ids | {same.id, higher.id},
                recent=(),
            )
            assert third.id == farther_higher.id
            fourth = await RankService.match(
                session,
                attacker,
                excluded=existing_ids | {same.id, higher.id, farther_higher.id},
                recent=(),
            )
            assert fourth.id == lower.id
        finally:
            await transaction.rollback()
