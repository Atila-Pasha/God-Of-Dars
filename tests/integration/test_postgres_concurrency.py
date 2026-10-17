import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.config import settings
from app.core.enums import AttackStatus, NotificationStatus, ResourceType, TeacherStatus
from app.db.session import AsyncSessionLocal, engine
from app.models.attack import Attack
from app.models.castle import Castle
from app.models.daily_quest import DailyQuest, DailyQuestProgress
from app.models.defense import Defense
from app.models.mine import Mine
from app.models.notification import Notification
from app.models.resource import Resource
from app.models.reward import Reward
from app.models.shield import Shield
from app.models.study_pack import StudyPack
from app.models.study_session import StudySession
from app.models.teacher import Teacher
from app.models.transaction import Transaction
from app.models.user import User
from app.models.user_teacher import UserTeacher
from app.services.attack_service import AttackService
from app.services.daily_quest_service import DailyQuestService
from app.services.mine_service import MineService
from app.services.notification_service import NotificationService
from app.services.referral_service import ReferralService
from app.services.reward_service import RewardService, RewardSpec
from app.services.school_errors import AttackInProgress, InsufficientCoins
from app.services.shield_service import ShieldService
from app.services.study_service import StudyAlreadyActive, StudyService
from app.workers.attack_resolver import (
    _is_retryable,
    _record_failure,
    resolve_due_attacks,
)
from app.workers.notification_worker import process_due_notifications

pytestmark = pytest.mark.skipif(
    not settings.DATABASE_URL.startswith("postgresql"),
    reason="requires PostgreSQL",
)


@pytest.fixture(autouse=True)
async def isolate_postgres_connections():
    await engine.dispose()
    yield
    await engine.dispose()


async def _user(coin: int = 0) -> int:
    async with AsyncSessionLocal() as session, session.begin():
        user = User(
            telegram_user_id=int(uuid4().int % 2_000_000_000),
            first_name="concurrency",
        )
        user.resources = Resource(coin=coin)
        session.add(user)
        await session.flush()
        return user.id


async def _cleanup(user_ids: list[int], *, pack_key: str | None = None) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                delete(Transaction).where(Transaction.user_id.in_(user_ids))
            )
            await session.execute(delete(Reward).where(Reward.user_id.in_(user_ids)))
            await session.execute(
                delete(Notification).where(Notification.recipient_user_id.in_(user_ids))
            )
            await session.execute(delete(User).where(User.id.in_(user_ids)))
            if pack_key is not None:
                await session.execute(
                    delete(StudyPack).where(StudyPack.key == pack_key)
                )


@pytest.mark.asyncio
async def test_concurrent_resource_debit_allows_only_one_spend() -> None:
    user_id = await _user(coin=100)

    async def spend() -> str:
        async with AsyncSessionLocal() as session:
            try:
                async with session.begin():
                    from app.services.resource_service import ResourceService

                    await ResourceService.debit(
                        session,
                        None,
                        user_id=user_id,
                        resource_type=ResourceType.COIN,
                        amount=100,
                        reason="TEST_SPEND",
                    )
                return "ok"
            except InsufficientCoins:
                return "insufficient"

    try:
        results = await asyncio.gather(spend(), spend())
        assert sorted(results) == ["insufficient", "ok"]
    finally:
        await _cleanup([user_id])


@pytest.mark.asyncio
async def test_concurrent_reward_same_reference_is_idempotent() -> None:
    user_id = await _user()

    async def grant() -> bool:
        async with AsyncSessionLocal() as session, session.begin():
            result = await RewardService().grant(
                session,
                user_id=user_id,
                spec=RewardSpec(ResourceType.COIN, 7),
                source="TEST",
                reference_type="EVENT",
                reference_id=9001,
            )
            return result.created

    try:
        assert sorted(await asyncio.gather(grant(), grant())) == [False, True]
        async with AsyncSessionLocal() as session:
            assert (
                await session.scalar(
                    select(Resource.coin).where(Resource.user_id == user_id)
                )
                == 7
            )
    finally:
        await _cleanup([user_id])


@pytest.mark.asyncio
async def test_concurrent_mine_collect_consumes_window_once() -> None:
    user_id = await _user()
    async with AsyncSessionLocal() as session, session.begin():
        mine = Mine(
            user_id=user_id,
            last_collected_at=datetime.now(UTC) - timedelta(minutes=10),
        )
        session.add(mine)

    async def collect() -> tuple[int, int, int]:
        async with AsyncSessionLocal() as session, session.begin():
            _, amounts = await MineService().collect(session, user_id)
            return amounts

    try:
        results = await asyncio.gather(collect(), collect())
        assert sum(sum(item) for item in results) > 0
        assert sum(sum(item) for item in results) == max(sum(item) for item in results)
    finally:
        await _cleanup([user_id])


@pytest.mark.asyncio
async def test_full_mine_waits_for_collection_before_next_cycle() -> None:
    user_id = await _user()
    cap = MineService().config.mine_max_catchup_minutes
    async with AsyncSessionLocal() as session, session.begin():
        session.add(
            Mine(
                user_id=user_id,
                level=1,
                last_collected_at=datetime.now(UTC) - timedelta(days=2),
                today_coin=cap * 2,
                daily_produced_minutes=cap,
            )
        )

    try:
        async with AsyncSessionLocal() as session, session.begin():
            snapshot = await MineService().open(session, user_id)
            assert snapshot.daily_produced_minutes == cap
            assert snapshot.today_coin == cap * 2

        async with AsyncSessionLocal() as session, session.begin():
            snapshot, amounts = await MineService().collect(
                session, user_id, resource_type=ResourceType.COIN
            )
            assert amounts == (cap * 2, 0, 0)
            assert snapshot.daily_produced_minutes == 0

        async with AsyncSessionLocal() as session, session.begin():
            mine = await session.scalar(select(Mine).where(Mine.user_id == user_id))
            assert mine is not None
            mine.last_collected_at -= timedelta(minutes=10)

        async with AsyncSessionLocal() as session, session.begin():
            snapshot = await MineService().open(session, user_id)
            assert snapshot.daily_produced_minutes == 10
            assert snapshot.today_coin == 20
    finally:
        await _cleanup([user_id])


@pytest.mark.asyncio
async def test_concurrent_study_start_has_one_active_session() -> None:
    user_id = await _user()
    pack_key = f"concurrency-{uuid4().hex[:12]}"
    async with AsyncSessionLocal() as session, session.begin():
        session.add(
            StudyPack(
                key=pack_key,
                name="concurrency",
                duration_minutes=60,
                reward_resource="COIN",
                reward_amount=1,
            )
        )

    async def start() -> str:
        async with AsyncSessionLocal() as session:
            try:
                async with session.begin():
                    await StudyService().start(session, user_id, pack_key)
                return "ok"
            except StudyAlreadyActive:
                return "active"
            except IntegrityError:
                return "active"

    try:
        assert sorted(await asyncio.gather(start(), start())) == ["active", "ok"]
        async with AsyncSessionLocal() as session:
            count = await session.scalar(
                select(func.count(StudySession.id)).where(
                    StudySession.user_id == user_id,
                    StudySession.completed_at.is_(None),
                )
            )
            assert count == 1
    finally:
        await _cleanup([user_id], pack_key=pack_key)


@pytest.mark.asyncio
async def test_concurrent_referral_reward_is_one_time() -> None:
    referrer_id = await _user()
    referred_id = await _user()

    async def apply() -> bool:
        async with AsyncSessionLocal() as session, session.begin():
            result = await ReferralService(
                inviter_reward=RewardSpec(ResourceType.COIN, 3)
            ).apply(
                session,
                referred_user_id=referred_id,
                referrer_id=referrer_id,
            )
            return result.applied

    try:
        assert sorted(await asyncio.gather(apply(), apply())) == [False, True]
        async with AsyncSessionLocal() as session:
            assert (
                await session.scalar(
                    select(Resource.coin).where(Resource.user_id == referrer_id)
                )
                == 3
            )
    finally:
        await _cleanup([referrer_id, referred_id])


@pytest.mark.asyncio
async def test_concurrent_daily_quest_event_and_claim_are_idempotent() -> None:
    user_id = await _user()
    quest_service = DailyQuestService()
    async with AsyncSessionLocal() as session, session.begin():
        quest = await quest_service.create(
            session,
            activity_date=quest_service.today(),
            quest_type="DAILY_LOGIN",
            title="concurrency quest",
            target=1,
            rewards={"COIN": 5},
        )
        quest_id = quest.id

    async def record() -> None:
        async with AsyncSessionLocal() as session, session.begin():
            await DailyQuestService().record_event(
                session,
                user_id=user_id,
                event_type="DAILY_LOGIN",
                event_id="same-event",
            )

    try:
        await asyncio.gather(record(), record())
        async with AsyncSessionLocal() as session:
            progress_id = await session.scalar(
                select(DailyQuestProgress.id).where(
                    DailyQuestProgress.user_id == user_id,
                    DailyQuestProgress.quest_id == quest_id,
                )
            )

        async def claim() -> bool:
            async with AsyncSessionLocal() as session, session.begin():
                return (
                    await DailyQuestService().claim(
                        session,
                        user_id=user_id,
                        progress_id=progress_id,
                    )
                    is not None
                )

        assert sorted(await asyncio.gather(claim(), claim())) == [False, True]
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(DailyQuest).where(DailyQuest.id == quest_id))
        await _cleanup([user_id])


@pytest.mark.asyncio
async def test_two_postgres_workers_resolve_one_attack() -> None:
    attacker_id = await _user()
    target_id = await _user(coin=10)
    teacher_id = None
    attack_id = None
    async with AsyncSessionLocal() as session, session.begin():
        teacher = Teacher(
            name=f"concurrency-teacher-{uuid4().hex[:8]}",
            damage=10,
            max_hp=100,
            purchase_price=1,
            upgrade_price=1,
        )
        attacker = await session.get(User, attacker_id)
        target = await session.get(User, target_id)
        attacker.castle = Castle(
            strength=100,
            defense=Defense(defense_power=0),
        )
        target.castle = Castle(
            strength=100,
            defense=Defense(defense_power=0),
        )
        owned = UserTeacher(
            user_id=attacker_id,
            teacher=teacher,
            current_hp=100,
            status=TeacherStatus.ACTIVE,
        )
        session.add(owned)
        await session.flush()
        attack = Attack(
            attacker_id=attacker_id,
            target_id=target_id,
            teacher_id=owned.id,
            status=AttackStatus.PENDING,
            resolve_at=datetime.now(UTC) - timedelta(seconds=1),
            teacher_damage_snapshot=10,
            target_castle_strength_snapshot=100,
            target_defense_power_snapshot=0,
        )
        session.add(attack)
        await session.flush()
        teacher_id = teacher.id
        attack_id = attack.id

    async def resolve():
        async with AsyncSessionLocal() as session, session.begin():
            return await AttackService().resolve_pending_attack(session, attack_id)

    try:
        results = await asyncio.gather(resolve(), resolve())
        assert sum(result is not None for result in results) == 1
        async with AsyncSessionLocal() as session:
            row = await session.get(Attack, attack_id)
            assert row.status is AttackStatus.RESOLVED
            assert (
                await session.scalar(
                    select(func.count(Transaction.id)).where(
                        Transaction.reference_type == "ATTACK",
                        Transaction.reference_id == attack_id,
                    )
                )
                == 3
            )
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(delete(Attack).where(Attack.id == attack_id))
                await session.execute(
                    delete(Transaction).where(
                        Transaction.user_id.in_([attacker_id, target_id])
                    )
                )
                await session.execute(
                    delete(User).where(User.id.in_([attacker_id, target_id]))
                )
                if teacher_id is not None:
                    await session.execute(
                        delete(Teacher).where(Teacher.id == teacher_id)
                    )


async def _attack_fixture() -> tuple[int, int, int, int]:
    attacker_id = await _user()
    target_id = await _user(coin=100)
    async with AsyncSessionLocal() as session, session.begin():
        teacher = Teacher(
            name=f"active-teacher-{uuid4().hex[:8]}",
            damage=10,
            max_hp=100,
            purchase_price=1,
            upgrade_price=1,
        )
        attacker = await session.get(User, attacker_id)
        target = await session.get(User, target_id)
        attacker.castle = Castle(strength=100, defense=Defense(defense_power=0))
        target.castle = Castle(strength=100, defense=Defense(defense_power=0))
        owned = UserTeacher(
            user_id=attacker_id,
            teacher=teacher,
            current_hp=100,
            status=TeacherStatus.ACTIVE,
        )
        session.add(owned)
        await session.flush()
        return attacker_id, target_id, owned.id, teacher.id


@pytest.mark.asyncio
async def test_attack_previews_do_not_lock_owned_or_shared_teacher_rows() -> None:
    attacker_id, target_id, owned_id, teacher_id = await _attack_fixture()
    try:
        async with AsyncSessionLocal() as session:
            attacker_telegram_id = await session.scalar(
                select(User.telegram_user_id).where(User.id == attacker_id)
            )
            target_telegram_id = await session.scalar(
                select(User.telegram_user_id).where(User.id == target_id)
            )
            teacher_name = await session.scalar(
                select(Teacher.name).where(Teacher.id == teacher_id)
            )
            service = AttackService()
            await service.preview_by_teacher_ids(
                session,
                attacker_telegram_id=attacker_telegram_id,
                target_id=target_id,
                teacher_ids=[owned_id],
            )
            await service.preview_by_telegram_id(
                session,
                attacker_telegram_id=attacker_telegram_id,
                target_telegram_id=target_telegram_id,
                teacher_name=teacher_name,
            )
            # Keep the preview transaction open, as a slow Telegram reply would.
            async with AsyncSessionLocal() as concurrent:
                assert (
                    await concurrent.scalar(
                        select(UserTeacher.id)
                        .where(UserTeacher.id == owned_id)
                        .with_for_update(nowait=True)
                    )
                    == owned_id
                )
                assert (
                    await concurrent.scalar(
                        select(Teacher.id)
                        .where(Teacher.id == teacher_id)
                        .with_for_update(nowait=True)
                    )
                    == teacher_id
                )
                await concurrent.rollback()
            await session.rollback()

            # Real attacks still lock the owned copy, never the shared catalog.
            owned = await service.teachers.get_owned_by_name_for_update(
                session, attacker_id, teacher_name
            )
            assert owned.id == owned_id
            async with AsyncSessionLocal() as concurrent:
                assert (
                    await concurrent.scalar(
                        select(Teacher.id)
                        .where(Teacher.id == teacher_id)
                        .with_for_update(nowait=True)
                    )
                    == teacher_id
                )
    finally:
        await _cleanup([attacker_id, target_id])


@pytest.mark.asyncio
async def test_destroyed_castle_direct_attack_raids_uncollected_mine_cargo() -> None:
    attacker_id, target_id, owned_id, teacher_id = await _attack_fixture()
    try:
        async with AsyncSessionLocal() as session, session.begin():
            resources = await session.scalar(
                select(Resource).where(Resource.user_id == target_id)
            )
            castle = await session.scalar(
                select(Castle).where(Castle.user_id == target_id)
            )
            resources.coin = 0
            castle.strength = 0
            session.add(
                Mine(
                    user_id=target_id,
                    today_coin=100,
                    today_diamond=10,
                    last_collected_at=datetime.now(UTC),
                )
            )
            await session.flush()

        async with AsyncSessionLocal() as session, session.begin():
            attacker_telegram_id = await session.scalar(
                select(User.telegram_user_id).where(User.id == attacker_id)
            )
            preview = await AttackService().preview_by_teacher_ids(
                session,
                attacker_telegram_id=attacker_telegram_id,
                target_id=target_id,
                teacher_ids=[owned_id],
            )
            assert preview.estimated_castle_damage == 0
            assert preview.estimated_teacher_injury == 0
            assert preview.mine_loot_coin > 0
            result = await AttackService().attack_by_ids(
                session,
                attacker_telegram_id=attacker_telegram_id,
                target_id=target_id,
                teacher_id=owned_id,
            )
            assert result.castle_damage == 0
            assert result.raid_damage > 0
            assert result.teacher_injury == 0
            assert result.mine_loot_coin > 0
            assert result.mine_loot_diamond > 0
            assert result.bot_bonus_coin == 0

        async with AsyncSessionLocal() as session:
            mine = await session.scalar(select(Mine).where(Mine.user_id == target_id))
            row = await session.get(Attack, result.attack.id)
            assert row.is_successful
            assert mine.today_coin == 100 - row.mine_loot_coin
            assert mine.today_diamond == 10 - row.mine_loot_diamond
            assert (
                await session.scalar(
                    select(Resource.coin).where(Resource.user_id == attacker_id)
                )
                == row.mine_loot_coin
            )
            assert (
                await session.scalar(
                    select(Resource.coin).where(Resource.user_id == target_id)
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count(Transaction.id)).where(
                        Transaction.reference_type == "ATTACK",
                        Transaction.reference_id == row.id,
                        Transaction.reason == "ATTACK_MINE_LOOT",
                    )
                )
                == 2
            )
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(
                delete(Attack).where(Attack.attacker_id == attacker_id)
            )
        await _cleanup([attacker_id, target_id])
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(Teacher).where(Teacher.id == teacher_id))


@pytest.mark.asyncio
@pytest.mark.parametrize("target_coin,expected_bonus", [(100, 0), (0, 10)])
async def test_destroyed_castle_pending_attack_still_loots_wallet(
    target_coin: int, expected_bonus: int
) -> None:
    attacker_id, target_id, owned_id, teacher_id = await _attack_fixture()
    try:
        async with AsyncSessionLocal() as session, session.begin():
            castle = await session.scalar(
                select(Castle).where(Castle.user_id == target_id)
            )
            castle.strength = 0
            resources = await session.scalar(
                select(Resource).where(Resource.user_id == target_id)
            )
            resources.coin = target_coin
            attack = Attack(
                attacker_id=attacker_id,
                target_id=target_id,
                teacher_id=owned_id,
                status=AttackStatus.PENDING,
                resolve_at=datetime.now(UTC),
                teacher_damage_snapshot=10,
                target_castle_strength_snapshot=0,
                target_defense_power_snapshot=0,
            )
            session.add(attack)
            await session.flush()
            attack_id = attack.id

        async with AsyncSessionLocal() as session, session.begin():
            result = await AttackService().resolve_pending_attack(session, attack_id)
            assert result is not None
            assert result.castle_damage == 0
            assert result.raid_damage == 10
            assert result.teacher_injury == 0
            assert result.loot_coin > 0
            assert result.bot_bonus_coin == expected_bonus

        async with AsyncSessionLocal() as session:
            row = await session.get(Attack, attack_id)
            assert row.is_successful
            assert await session.scalar(
                select(Resource.coin).where(Resource.user_id == target_id)
            ) == target_coin - (row.loot_coin - expected_bonus)
            assert (
                await session.scalar(
                    select(Resource.coin).where(Resource.user_id == attacker_id)
                )
                == row.loot_coin
            )
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(
                delete(Attack).where(Attack.attacker_id == attacker_id)
            )
        await _cleanup([attacker_id, target_id])
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(Teacher).where(Teacher.id == teacher_id))


@pytest.mark.asyncio
async def test_preview_drops_defense_for_teachers_after_castle_falls() -> None:
    attacker_id, target_id, first_owned_id, first_teacher_id = await _attack_fixture()
    second_teacher_id = None
    try:
        async with AsyncSessionLocal() as session, session.begin():
            castle = await session.scalar(
                select(Castle).where(Castle.user_id == target_id)
            )
            castle.strength = 5
            defense = await session.scalar(
                select(Defense).where(Defense.castle_id == castle.id)
            )
            defense.defense_power = 5
            teacher = Teacher(
                name=f"raid-preview-{uuid4().hex[:8]}",
                damage=10,
                max_hp=100,
                purchase_price=1,
                upgrade_price=1,
            )
            owned = UserTeacher(
                user_id=attacker_id,
                teacher=teacher,
                current_hp=100,
                status=TeacherStatus.ACTIVE,
            )
            session.add(owned)
            await session.flush()
            second_owned_id, second_teacher_id = owned.id, teacher.id
            attacker_telegram_id = await session.scalar(
                select(User.telegram_user_id).where(User.id == attacker_id)
            )

        async with AsyncSessionLocal() as session, session.begin():
            service = AttackService()
            preview = await service.preview_by_teacher_ids(
                session,
                attacker_telegram_id=attacker_telegram_id,
                target_id=target_id,
                teacher_ids=[first_owned_id, second_owned_id],
            )
            assert preview.estimated_castle_damage == 5
            assert preview.estimated_raid_damage == 10
            result = await service.attack_by_ids(
                session,
                attacker_telegram_id=attacker_telegram_id,
                target_id=target_id,
                teacher_id=first_owned_id,
                teacher_ids=[first_owned_id, second_owned_id],
            )
            assert (result.castle_damage, result.raid_damage) == (5, 10)
            assert preview.loot_coin == result.loot_coin
            assert preview.loot_diamond == result.loot_diamond
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(
                delete(Attack).where(Attack.attacker_id == attacker_id)
            )
        await _cleanup([attacker_id, target_id])
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(
                delete(Teacher).where(
                    Teacher.id.in_([first_teacher_id, second_teacher_id])
                )
            )


@pytest.mark.asyncio
async def test_mine_collection_and_raid_cannot_duplicate_cargo() -> None:
    attacker_id, target_id, owned_id, teacher_id = await _attack_fixture()
    try:
        async with AsyncSessionLocal() as session, session.begin():
            resources = await session.scalar(
                select(Resource).where(Resource.user_id == target_id)
            )
            castle = await session.scalar(
                select(Castle).where(Castle.user_id == target_id)
            )
            resources.coin = 0
            castle.strength = 0
            session.add(
                Mine(
                    user_id=target_id,
                    today_coin=100,
                    last_collected_at=datetime.now(UTC),
                )
            )
            attacker_telegram_id = await session.scalar(
                select(User.telegram_user_id).where(User.id == attacker_id)
            )

        async def raid() -> None:
            async with AsyncSessionLocal() as session, session.begin():
                await AttackService().attack_by_ids(
                    session,
                    attacker_telegram_id=attacker_telegram_id,
                    target_id=target_id,
                    teacher_id=owned_id,
                )

        async def collect() -> None:
            async with AsyncSessionLocal() as session, session.begin():
                await MineService().collect(session, target_id)

        await asyncio.gather(raid(), collect())
        async with AsyncSessionLocal() as session:
            mine = await session.scalar(select(Mine).where(Mine.user_id == target_id))
            attacker_coin = await session.scalar(
                select(Resource.coin).where(Resource.user_id == attacker_id)
            )
            target_coin = await session.scalar(
                select(Resource.coin).where(Resource.user_id == target_id)
            )
            assert attacker_coin + target_coin + mine.today_coin == 100
            assert attacker_coin > 0
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(
                delete(Attack).where(Attack.attacker_id == attacker_id)
            )
        await _cleanup([attacker_id, target_id])
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(Teacher).where(Teacher.id == teacher_id))


@pytest.mark.asyncio
async def test_injured_teacher_with_remaining_hp_can_launch_attack() -> None:
    attacker_id, target_id, owned_id, teacher_id = await _attack_fixture()
    try:
        async with AsyncSessionLocal() as session, session.begin():
            owned = await session.get(UserTeacher, owned_id)
            owned.current_hp = 30
            owned.status = TeacherStatus.INJURED

        async with AsyncSessionLocal() as session:
            telegram_id = await session.scalar(
                select(User.telegram_user_id).where(User.id == attacker_id)
            )
            service = AttackService()
            available = await service.available_attack_teachers(
                session, attacker_telegram_id=telegram_id
            )
            assert owned_id in {teacher.id for teacher in available}
            preview = await service.preview_by_teacher_ids(
                session,
                attacker_telegram_id=telegram_id,
                target_id=target_id,
                teacher_ids=[owned_id],
            )
            assert preview.teacher_id == owned_id
            launch = await service.start_attack_by_ids(
                session,
                attacker_telegram_id=telegram_id,
                target_id=target_id,
                teacher_ids=[owned_id],
            )
            assert len(launch.attack_ids) == 1
            await session.rollback()
    finally:
        await _cleanup([attacker_id, target_id])
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(Teacher).where(Teacher.id == teacher_id))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,retryable",
    [
        (AttackStatus.PROCESSING, True),
        (AttackStatus.FAILED, True),
        (AttackStatus.FAILED, False),
    ],
)
async def test_active_attack_states_control_new_attack(
    status: AttackStatus, retryable: bool
) -> None:
    attacker_id, target_id, owned_id, teacher_id = await _attack_fixture()
    attack_id = None
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                attack = Attack(
                    attacker_id=attacker_id,
                    target_id=target_id,
                    teacher_id=owned_id,
                    status=status,
                    processing_at=datetime.now(UTC)
                    if status is AttackStatus.PROCESSING
                    else None,
                    failed_at=datetime.now(UTC)
                    if status is AttackStatus.FAILED
                    else None,
                    next_retry_at=(
                        datetime.now(UTC) + timedelta(minutes=1)
                        if retryable and status is AttackStatus.FAILED
                        else None
                    ),
                    resolve_at=datetime.now(UTC),
                    teacher_damage_snapshot=10,
                    target_castle_strength_snapshot=100,
                    target_defense_power_snapshot=0,
                )
                session.add(attack)
                await session.flush()
                attack_id = attack.id
        async with AsyncSessionLocal() as session:
            async with session.begin():
                if retryable:
                    with pytest.raises(AttackInProgress):
                        await AttackService().start_attack_by_ids(
                            session,
                            attacker_telegram_id=(
                                await session.scalar(
                                    select(User.telegram_user_id).where(
                                        User.id == attacker_id
                                    )
                                )
                            ),
                            target_id=target_id,
                            teacher_ids=[owned_id],
                        )
                else:
                    result = await AttackService().start_attack_by_ids(
                        session,
                        attacker_telegram_id=(
                            await session.scalar(
                                select(User.telegram_user_id).where(
                                    User.id == attacker_id
                                )
                            )
                        ),
                        target_id=target_id,
                        teacher_ids=[owned_id],
                    )
                    assert result.resolve_at > datetime.now(UTC)
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(delete(Attack).where(Attack.id == attack_id))
                await session.execute(
                    delete(Attack).where(
                        Attack.attacker_id.in_([attacker_id, target_id])
                    )
                )
                await session.execute(
                    delete(Transaction).where(
                        Transaction.user_id.in_([attacker_id, target_id])
                    )
                )
                await session.execute(
                    delete(User).where(User.id.in_([attacker_id, target_id]))
                )
                await session.execute(delete(Teacher).where(Teacher.id == teacher_id))


@pytest.mark.asyncio
async def test_concurrent_attack_starts_are_serialized_by_user_lock() -> None:
    attacker_id, target_id, owned_id, teacher_id = await _attack_fixture()
    telegram_id = None
    try:
        async with AsyncSessionLocal() as session:
            telegram_id = await session.scalar(
                select(User.telegram_user_id).where(User.id == attacker_id)
            )

        async def start():
            async with AsyncSessionLocal() as session:
                try:
                    async with session.begin():
                        await AttackService().start_attack_by_ids(
                            session,
                            attacker_telegram_id=telegram_id,
                            target_id=target_id,
                            teacher_ids=[owned_id],
                        )
                    return True
                except AttackInProgress:
                    return False

        assert sorted(await asyncio.gather(start(), start())) == [False, True]
        async with AsyncSessionLocal() as session:
            count = await session.scalar(
                select(func.count(Attack.id)).where(
                    Attack.attacker_id == attacker_id,
                    Attack.status == AttackStatus.PENDING,
                )
            )
            assert count == 1
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    delete(Attack).where(Attack.attacker_id == attacker_id)
                )
                await session.execute(
                    delete(Transaction).where(
                        Transaction.user_id.in_([attacker_id, target_id])
                    )
                )
                await session.execute(
                    delete(User).where(User.id.in_([attacker_id, target_id]))
                )
                await session.execute(delete(Teacher).where(Teacher.id == teacher_id))


@pytest.mark.asyncio
async def test_opposing_direct_attacks_follow_shared_lock_order() -> None:
    first_id, second_id, first_teacher_id, first_catalog_id = await _attack_fixture()
    second_teacher_id = second_catalog_id = None
    try:
        async with AsyncSessionLocal() as session, session.begin():
            teacher = Teacher(
                name=f"reverse-teacher-{uuid4().hex[:8]}",
                damage=10,
                max_hp=100,
                purchase_price=1,
                upgrade_price=1,
            )
            owned = UserTeacher(
                user_id=second_id,
                teacher=teacher,
                current_hp=100,
                status=TeacherStatus.ACTIVE,
            )
            session.add(owned)
            await session.flush()
            second_teacher_id = owned.id
            second_catalog_id = teacher.id
            first_telegram_id = await session.scalar(
                select(User.telegram_user_id).where(User.id == first_id)
            )
            second_telegram_id = await session.scalar(
                select(User.telegram_user_id).where(User.id == second_id)
            )

        async def attack(telegram_id, target_id, teacher_id):
            async with AsyncSessionLocal() as session, session.begin():
                return await AttackService().attack_by_ids(
                    session,
                    attacker_telegram_id=telegram_id,
                    target_id=target_id,
                    teacher_id=teacher_id,
                )

        results = await asyncio.gather(
            attack(first_telegram_id, second_id, first_teacher_id),
            attack(second_telegram_id, first_id, second_teacher_id),
        )
        assert len(results) == 2
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    delete(Attack).where(Attack.attacker_id.in_([first_id, second_id]))
                )
                await session.execute(
                    delete(Transaction).where(
                        Transaction.user_id.in_([first_id, second_id])
                    )
                )
                await session.execute(
                    delete(User).where(User.id.in_([first_id, second_id]))
                )
                await session.execute(
                    delete(Teacher).where(Teacher.id == first_catalog_id)
                )
                if second_catalog_id is not None:
                    await session.execute(
                        delete(Teacher).where(Teacher.id == second_catalog_id)
                    )


@pytest.mark.asyncio
async def test_attack_resource_lock_prevents_stale_reward_overwrite() -> None:
    attacker_id, target_id, owned_id, teacher_id = await _attack_fixture()
    attack_id = None
    paused = asyncio.Event()
    reward_started = asyncio.Event()
    release = asyncio.Event()
    service = AttackService()
    original_receive = service.castle_service.receive_attack_damage

    async def receive_and_pause(
        session, user_id, incoming_damage, *, teacher_names=None, ignore_shield=False
    ):
        result = await original_receive(
            session,
            user_id,
            incoming_damage,
            teacher_names=teacher_names,
            ignore_shield=ignore_shield,
        )
        paused.set()
        await reward_started.wait()
        release.set()
        return result

    service.castle_service.receive_attack_damage = receive_and_pause
    try:
        async with AsyncSessionLocal() as session, session.begin():
            attack = Attack(
                attacker_id=attacker_id,
                target_id=target_id,
                teacher_id=owned_id,
                status=AttackStatus.PENDING,
                resolve_at=datetime.now(UTC),
                teacher_damage_snapshot=10,
                target_castle_strength_snapshot=100,
                target_defense_power_snapshot=0,
            )
            session.add(attack)
            await session.flush()
            attack_id = attack.id

        async def resolve():
            async with AsyncSessionLocal() as session, session.begin():
                return await service.resolve_pending_attack(session, attack_id)

        async def grant():
            await paused.wait()
            reward_started.set()
            async with AsyncSessionLocal() as session, session.begin():
                await RewardService().grant(
                    session,
                    user_id=target_id,
                    spec=RewardSpec(ResourceType.COIN, 7),
                    source="CONCURRENT_TEST",
                    reference_type="TEST",
                    reference_id=attack_id,
                )

        await asyncio.gather(resolve(), grant())
        async with AsyncSessionLocal() as session:
            final_balance = await session.scalar(
                select(Resource.coin).where(Resource.user_id == target_id)
            )
            target_ledger = await session.scalars(
                select(Transaction.amount).where(
                    Transaction.user_id == target_id,
                    Transaction.resource_type == ResourceType.COIN,
                )
            )
            assert final_balance == 100 + sum(target_ledger)
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(delete(Attack).where(Attack.id == attack_id))
                await session.execute(
                    delete(Transaction).where(
                        Transaction.user_id.in_([attacker_id, target_id])
                    )
                )
                await session.execute(
                    delete(Reward).where(Reward.user_id.in_([attacker_id, target_id]))
                )
                await session.execute(
                    delete(User).where(User.id.in_([attacker_id, target_id]))
                )
                await session.execute(delete(Teacher).where(Teacher.id == teacher_id))


@pytest.mark.asyncio
async def test_postgres_deadlock_is_real_and_attack_retry_is_bounded() -> None:
    first_id = await _user()
    second_id = await _user()
    first_locked = asyncio.Event()
    second_locked = asyncio.Event()

    async def lock_in_order(first: int, second: int) -> BaseException | None:
        try:
            async with AsyncSessionLocal() as session, session.begin():
                await session.execute(
                    text("SELECT id FROM users WHERE id = :id FOR UPDATE"),
                    {"id": first},
                )
                (first_locked if first == first_id else second_locked).set()
                await asyncio.wait_for(
                    (second_locked if first == first_id else first_locked).wait(),
                    timeout=5,
                )
                await session.execute(
                    text("SELECT id FROM users WHERE id = :id FOR UPDATE"),
                    {"id": second},
                )
        except BaseException as exc:
            return exc
        return None

    try:
        errors = await asyncio.wait_for(
            asyncio.gather(
                lock_in_order(first_id, second_id),
                lock_in_order(second_id, first_id),
            ),
            timeout=10,
        )
        deadlocks = [
            error
            for error in errors
            if isinstance(error, DBAPIError)
            and getattr(getattr(error, "orig", None), "sqlstate", None) == "40P01"
        ]
        assert len(deadlocks) == 1
        assert _is_retryable(deadlocks[0])
        async with AsyncSessionLocal() as session, session.begin():
            attack = Attack(
                attacker_id=first_id,
                target_id=second_id,
                status=AttackStatus.PROCESSING,
                processing_at=datetime.now(UTC),
                resolve_at=datetime.now(UTC),
                teacher_damage_snapshot=0,
                target_castle_strength_snapshot=0,
                target_defense_power_snapshot=0,
            )
            session.add(attack)
            await session.flush()
            retry_attack_id = attack.id
        async with AsyncSessionLocal() as session:
            await _record_failure(session, retry_attack_id, deadlocks[0])
        async with AsyncSessionLocal() as session:
            retry_attack = await session.get(Attack, retry_attack_id)
            assert retry_attack.status is AttackStatus.FAILED
            assert retry_attack.retry_count == 1
            assert retry_attack.next_retry_at is not None
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(Attack).where(Attack.id == retry_attack_id))
    finally:
        await _cleanup([first_id, second_id])


@pytest.mark.asyncio
async def test_postgres_serialization_failure_is_transient() -> None:
    user_id = await _user(coin=10)
    barrier = asyncio.Barrier(2)

    async def update_serializable() -> BaseException | None:
        try:
            async with AsyncSessionLocal() as session, session.begin():
                await session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                )
                await session.scalar(
                    select(Resource.coin).where(Resource.user_id == user_id)
                )
                await barrier.wait()
                await session.execute(
                    text(
                        "UPDATE resources SET coin = coin + 1 WHERE user_id = :user_id"
                    ),
                    {"user_id": user_id},
                )
        except BaseException as exc:
            return exc
        return None

    try:
        errors = await asyncio.gather(update_serializable(), update_serializable())
        transient = [
            error
            for error in errors
            if isinstance(error, DBAPIError)
            and getattr(getattr(error, "orig", None), "sqlstate", None) == "40001"
        ]
        assert len(transient) == 1
        assert _is_retryable(transient[0])
    finally:
        await _cleanup([user_id])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_coin", "expected_bonus", "expected_transactions"),
    [(10, 0, 3), (0, 10, 2)],
)
async def test_stale_processing_attack_recovers_without_duplicate_ledger(
    target_coin: int, expected_bonus: int, expected_transactions: int
) -> None:
    attacker_id = await _user()
    target_id = await _user(coin=target_coin)
    attack_id = None
    teacher_id = None
    async with AsyncSessionLocal() as session, session.begin():
        teacher = Teacher(
            name=f"stale-teacher-{uuid4().hex[:8]}",
            damage=10,
            max_hp=100,
            purchase_price=1,
            upgrade_price=1,
        )
        owned = UserTeacher(
            user_id=attacker_id,
            teacher=teacher,
            current_hp=100,
            status=TeacherStatus.ACTIVE,
        )
        attacker = await session.get(User, attacker_id)
        target = await session.get(User, target_id)
        attacker.castle = Castle(strength=100, defense=Defense(defense_power=0))
        target.castle = Castle(strength=100, defense=Defense(defense_power=0))
        session.add(owned)
        await session.flush()
        attack = Attack(
            attacker_id=attacker_id,
            target_id=target_id,
            teacher_id=owned.id,
            status=AttackStatus.PROCESSING,
            processing_at=datetime.now(UTC) - timedelta(hours=1),
            resolve_at=datetime.now(UTC) - timedelta(hours=1),
            teacher_damage_snapshot=10,
            target_castle_strength_snapshot=100,
            target_defense_power_snapshot=0,
        )
        session.add(attack)
        await session.flush()
        attack_id, teacher_id = attack.id, teacher.id

    try:
        await resolve_due_attacks(AsyncMock(), batch_size=1)
        async with AsyncSessionLocal() as session:
            row = await session.get(Attack, attack_id)
            assert row.status is AttackStatus.RESOLVED
            assert row.bot_bonus_coin == expected_bonus
            assert row.loot_coin == (10 if target_coin == 0 else 1)
            assert (
                await session.scalar(
                    select(Resource.coin).where(Resource.user_id == attacker_id)
                )
                == row.loot_coin
            )
            assert await session.scalar(
                select(Resource.coin).where(Resource.user_id == target_id)
            ) == target_coin - (row.loot_coin - row.bot_bonus_coin)
            assert (
                await session.scalar(
                    select(func.count(Transaction.id)).where(
                        Transaction.reference_type == "ATTACK",
                        Transaction.reference_id == attack_id,
                    )
                )
                == expected_transactions
            )
            assert (
                await session.scalar(
                    select(func.count(Notification.id)).where(
                        Notification.idempotency_key.like(
                            f"ATTACK_RESULT:{attack_id}:%"
                        )
                    )
                )
                == 2
            )
            assert (
                await session.scalar(
                    select(func.count(Notification.id)).where(
                        Notification.idempotency_key
                        == f"ATTACK_TEACHER_INJURY:{attack_id}:ATTACKER"
                    )
                )
                == 1
            )
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(delete(Attack).where(Attack.id == attack_id))
                await session.execute(
                    delete(Transaction).where(
                        Transaction.user_id.in_([attacker_id, target_id])
                    )
                )
                await session.execute(
                    delete(User).where(User.id.in_([attacker_id, target_id]))
                )
                await session.execute(delete(Teacher).where(Teacher.id == teacher_id))


@pytest.mark.asyncio
async def test_empty_target_bonus_is_awarded_once_for_multiple_teachers() -> None:
    attacker_id = await _user()
    target_id = await _user()
    attack_ids: list[int] = []
    teacher_ids: list[int] = []
    async with AsyncSessionLocal() as session, session.begin():
        attacker = await session.get(User, attacker_id)
        target = await session.get(User, target_id)
        attacker.castle = Castle(strength=100, defense=Defense(defense_power=0))
        target.castle = Castle(strength=100, defense=Defense(defense_power=0))
        command_id = str(uuid4())
        for _ in range(2):
            teacher = Teacher(
                name=f"empty-target-{uuid4().hex[:8]}",
                damage=10,
                max_hp=100,
                purchase_price=1,
                upgrade_price=1,
            )
            owned = UserTeacher(
                user_id=attacker_id,
                teacher=teacher,
                current_hp=100,
                status=TeacherStatus.ACTIVE,
            )
            session.add(owned)
            await session.flush()
            attack = Attack(
                attacker_id=attacker_id,
                target_id=target_id,
                teacher_id=owned.id,
                status=AttackStatus.PENDING,
                resolve_at=datetime.now(UTC),
                attack_command_id=command_id,
                teacher_damage_snapshot=10,
                target_castle_strength_snapshot=100,
                target_defense_power_snapshot=0,
            )
            session.add(attack)
            await session.flush()
            attack_ids.append(attack.id)
            teacher_ids.append(teacher.id)

    try:
        service = AttackService()
        for attack_id in attack_ids:
            async with AsyncSessionLocal() as session, session.begin():
                await service.resolve_pending_attack(session, attack_id)
        async with AsyncSessionLocal() as session:
            rows = list(
                await session.scalars(select(Attack).where(Attack.id.in_(attack_ids)))
            )
            assert sum(row.bot_bonus_coin for row in rows) == 10
            assert (
                await session.scalar(
                    select(Resource.coin).where(Resource.user_id == attacker_id)
                )
                == 10
            )
            assert (
                await session.scalar(
                    select(func.count(Transaction.id)).where(
                        Transaction.user_id == attacker_id,
                        Transaction.reason == "ATTACK_EMPTY_TARGET_BONUS",
                    )
                )
                == 1
            )
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(Attack).where(Attack.id.in_(attack_ids)))
        await _cleanup([attacker_id, target_id])
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(Teacher).where(Teacher.id.in_(teacher_ids)))


@pytest.mark.asyncio
async def test_notification_outbox_is_idempotent_and_two_workers_send_once() -> None:
    user_id = await _user()
    bot = AsyncMock()

    async def enqueue() -> None:
        async with AsyncSessionLocal() as session, session.begin():
            await NotificationService().enqueue(
                session,
                notification_type="TEST",
                recipient_user_id=user_id,
                idempotency_key="TEST:notification:1",
                payload={"chat_id": 123, "text": "hello"},
            )

    try:
        await asyncio.gather(enqueue(), enqueue())
        await asyncio.gather(
            process_due_notifications(bot, batch_size=1, recipient_user_id=user_id),
            process_due_notifications(bot, batch_size=1, recipient_user_id=user_id),
        )
        assert bot.send_message.await_count == 1
        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(Notification).where(
                    Notification.idempotency_key == "TEST:notification:1"
                )
            )
            assert row.status is NotificationStatus.SENT
            assert row.attempts == 1
    finally:
        await _cleanup([user_id])


@pytest.mark.asyncio
async def test_notification_failure_retries_and_preserves_idempotency() -> None:
    user_id = await _user()
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=[TimeoutError("telegram timeout"), None])
    try:
        async with AsyncSessionLocal() as session, session.begin():
            await NotificationService().enqueue(
                session,
                notification_type="TEST",
                recipient_user_id=user_id,
                idempotency_key="TEST:notification:retry",
                payload={"chat_id": 123, "text": "retry"},
            )
        await process_due_notifications(bot, batch_size=1, recipient_user_id=user_id)
        async with AsyncSessionLocal() as session, session.begin():
            row = await session.scalar(
                select(Notification)
                .where(Notification.idempotency_key == "TEST:notification:retry")
                .with_for_update()
            )
            row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await process_due_notifications(bot, batch_size=1, recipient_user_id=user_id)
        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(Notification).where(
                    Notification.idempotency_key == "TEST:notification:retry"
                )
            )
            assert row.status is NotificationStatus.SENT
            assert row.attempts == 2
            assert bot.send_message.await_count == 2
    finally:
        await _cleanup([user_id])


@pytest.mark.asyncio
async def test_notification_crash_window_is_at_least_once() -> None:
    user_id = await _user()
    deliveries = []
    bot = AsyncMock()

    async def delivered_then_crash(**kwargs):
        deliveries.append(kwargs)
        raise RuntimeError("crash after provider accepted message")

    bot.send_message = AsyncMock(side_effect=delivered_then_crash)
    try:
        async with AsyncSessionLocal() as session, session.begin():
            await NotificationService().enqueue(
                session,
                notification_type="TEST",
                recipient_user_id=user_id,
                idempotency_key="TEST:notification:crash-window",
                payload={"chat_id": 123, "text": "may duplicate"},
            )
        await process_due_notifications(bot, batch_size=1, recipient_user_id=user_id)
        async with AsyncSessionLocal() as session, session.begin():
            row = await session.scalar(
                select(Notification)
                .where(Notification.idempotency_key == "TEST:notification:crash-window")
                .with_for_update()
            )
            row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await process_due_notifications(bot, batch_size=1, recipient_user_id=user_id)
        assert len(deliveries) == 2
    finally:
        await _cleanup([user_id])


@pytest.mark.asyncio
async def test_stale_processing_notification_is_recovered_after_worker_restart() -> (
    None
):
    user_id = await _user()
    bot = AsyncMock()
    try:
        async with AsyncSessionLocal() as session, session.begin():
            row = Notification(
                notification_type="TEST",
                recipient_user_id=user_id,
                idempotency_key="TEST:notification:stale",
                payload={"chat_id": 123, "text": "recovered"},
                status=NotificationStatus.PROCESSING,
                attempts=1,
                processing_at=datetime.now(UTC) - timedelta(hours=1),
            )
            session.add(row)
        await process_due_notifications(bot, batch_size=1, recipient_user_id=user_id)
        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(Notification).where(
                    Notification.idempotency_key == "TEST:notification:stale"
                )
            )
            assert row.status is NotificationStatus.SENT
            assert row.attempts == 2
            assert bot.send_message.await_count == 1
    finally:
        await _cleanup([user_id])


@pytest.mark.asyncio
@pytest.mark.parametrize("shield_before_resolution", [True, False])
async def test_shield_activation_does_not_cancel_pending_attack(
    shield_before_resolution: bool,
) -> None:
    attacker_id = await _user()
    target_id = await _user(coin=10)
    attack_id = shield_id = teacher_id = None
    async with AsyncSessionLocal() as session, session.begin():
        teacher = Teacher(
            name=f"shield-teacher-{uuid4().hex[:8]}",
            damage=10,
            max_hp=100,
            purchase_price=1,
            upgrade_price=1,
        )
        shield = Shield(
            name=f"shield-{uuid4().hex[:8]}",
            reduction_percent=50,
            flat_absorption=0,
            purchase_price=1,
            unlock_level=1,
            duration_minutes=60,
        )
        attacker = await session.get(User, attacker_id)
        target = await session.get(User, target_id)
        attacker.castle = Castle(strength=100, defense=Defense(defense_power=0))
        target.castle = Castle(strength=100, defense=Defense(defense_power=0))
        owned = UserTeacher(
            user_id=attacker_id,
            teacher=teacher,
            current_hp=100,
            status=TeacherStatus.ACTIVE,
        )
        session.add_all([owned, shield])
        await session.flush()
        attack = Attack(
            attacker_id=attacker_id,
            target_id=target_id,
            teacher_id=owned.id,
            status=AttackStatus.PENDING,
            resolve_at=datetime.now(UTC) - timedelta(seconds=1),
            teacher_damage_snapshot=10,
            target_castle_strength_snapshot=100,
            target_defense_power_snapshot=0,
        )
        session.add(attack)
        await session.flush()
        attack_id, shield_id, teacher_id = attack.id, shield.id, teacher.id

    async def resolve() -> None:
        async with AsyncSessionLocal() as session, session.begin():
            await AttackService().resolve_pending_attack(session, attack_id)

    async def activate() -> None:
        async with AsyncSessionLocal() as session, session.begin():
            await ShieldService().buy(session, target_id, shield_id)

    try:
        if shield_before_resolution:
            await activate()
            await resolve()
        else:
            results = await asyncio.gather(
                resolve(), activate(), return_exceptions=True
            )
            assert not [result for result in results if isinstance(result, Exception)]
        async with AsyncSessionLocal() as session:
            attack = await session.get(Attack, attack_id)
            assert attack.status is AttackStatus.RESOLVED
            assert attack.result_damage > 0
            castle_strength = await session.scalar(
                select(Castle.strength).where(Castle.user_id == target_id)
            )
            assert castle_strength == 100 - attack.result_damage
            assert await session.scalar(
                select(func.count(Transaction.id)).where(
                    Transaction.reference_type == "ATTACK",
                    Transaction.reference_id == attack_id,
                )
            ) in (0, 3)
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(delete(Attack).where(Attack.id == attack_id))
                await session.execute(
                    delete(Transaction).where(
                        Transaction.user_id.in_([attacker_id, target_id])
                    )
                )
                await session.execute(
                    delete(User).where(User.id.in_([attacker_id, target_id]))
                )
                await session.execute(delete(Shield).where(Shield.id == shield_id))
                await session.execute(delete(Teacher).where(Teacher.id == teacher_id))


@pytest.mark.parametrize("currency", [ResourceType.COIN, ResourceType.DIAMOND])
async def test_failed_teacher_purchase_handler_does_not_commit_ownership(currency):
    from types import SimpleNamespace

    from app.bot.callbacks import ConfirmationCallback
    from app.bot.handlers.school import confirmation_callback_handler
    from app.bot.middlewares.database import DatabaseSessionMiddleware

    user_id = await _user()
    async with AsyncSessionLocal() as session, session.begin():
        teacher = Teacher(
            name=f"unaffordable-{uuid4().hex[:8]}",
            damage=10,
            max_hp=100,
            purchase_price=200,
            purchase_resource=currency,
            upgrade_price=10,
        )
        session.add(teacher)
        await session.flush()
        teacher_id = teacher.id
        telegram_id = await session.scalar(
            select(User.telegram_user_id).where(User.id == user_id)
        )
    try:
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=telegram_id),
            message=None,
            answer=AsyncMock(),
        )
        data = ConfirmationCallback(
            action="teacher_buy", target_id=teacher_id, decision="confirm"
        )

        async def handler(event, context):
            await confirmation_callback_handler(event, data, context["session"])

        await DatabaseSessionMiddleware()(handler, callback, {})
        callback.answer.assert_awaited_once()
        async with AsyncSessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count(UserTeacher.id)).where(
                        UserTeacher.user_id == user_id
                    )
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count(Transaction.id)).where(
                        Transaction.user_id == user_id
                    )
                )
                == 0
            )
    finally:
        await _cleanup([user_id])
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(Teacher).where(Teacher.id == teacher_id))


@pytest.mark.parametrize("currency", list(ResourceType))
async def test_preloaded_wallet_cannot_spend_a_committed_debit_again(currency):
    from app.repositories.user import UserRepository
    from app.services.resource_service import ResourceService

    user_id = await _user()
    field = currency.value.lower()
    async with AsyncSessionLocal() as session, session.begin():
        wallet = await session.scalar(
            select(Resource).where(Resource.user_id == user_id)
        )
        setattr(wallet, field, 100)
        telegram_id = await session.scalar(
            select(User.telegram_user_id).where(User.id == user_id)
        )
    try:
        async with AsyncSessionLocal() as stale:
            user = await UserRepository().get_by_telegram_user_id(stale, telegram_id)
            assert getattr(user.resources, field) == 100
            async with AsyncSessionLocal() as writer, writer.begin():
                await ResourceService.debit(
                    writer,
                    None,
                    user_id=user_id,
                    resource_type=currency,
                    amount=80,
                    reason="FIRST_SPEND",
                )
            with pytest.raises(InsufficientCoins):
                await ResourceService.debit(
                    stale,
                    user.resources,
                    user_id=user_id,
                    resource_type=currency,
                    amount=80,
                    reason="SECOND_SPEND",
                )
            await stale.rollback()
        async with AsyncSessionLocal() as session:
            assert (
                await session.scalar(
                    select(getattr(Resource, field)).where(Resource.user_id == user_id)
                )
                == 20
            )
            assert (
                await session.scalar(
                    select(func.sum(Transaction.amount)).where(
                        Transaction.user_id == user_id
                    )
                )
                == -80
            )
    finally:
        await _cleanup([user_id])


@pytest.mark.parametrize("currency", list(ResourceType))
async def test_reward_refresh_preserves_other_session_credit_and_local_changes(
    currency,
):
    from app.repositories.user import UserRepository

    user_id = await _user()
    async with AsyncSessionLocal() as session:
        telegram_id = await session.scalar(
            select(User.telegram_user_id).where(User.id == user_id)
        )
    try:
        async with AsyncSessionLocal() as stale:
            user = await UserRepository().get_by_telegram_user_id(stale, telegram_id)
            assert getattr(user.resources, currency.value.lower()) == 0
            async with AsyncSessionLocal() as writer, writer.begin():
                await RewardService().grant(
                    writer,
                    user_id=user_id,
                    spec=RewardSpec(currency, 7),
                    source="REFRESH_TEST",
                    reference_type="TEST",
                    reference_id=1,
                )
            for reference_id in (2, 3):
                await RewardService().grant(
                    stale,
                    user_id=user_id,
                    spec=RewardSpec(currency, 3),
                    source="REFRESH_TEST",
                    reference_type="TEST",
                    reference_id=reference_id,
                )
            await stale.commit()
        async with AsyncSessionLocal() as session:
            assert (
                await session.scalar(
                    select(getattr(Resource, currency.value.lower())).where(
                        Resource.user_id == user_id
                    )
                )
                == 13
            )
            assert (
                await session.scalar(
                    select(func.sum(Transaction.amount)).where(
                        Transaction.user_id == user_id
                    )
                )
                == 13
            )
    finally:
        await _cleanup([user_id])


@pytest.mark.parametrize(
    "status", [AttackStatus.PENDING, AttackStatus.PROCESSING, AttackStatus.FAILED]
)
async def test_teacher_sale_waits_for_active_attack_and_allows_finished_history(status):
    from app.services.teacher_service import TeacherService

    attacker_id, target_id, owned_id, teacher_id = await _attack_fixture()
    attack_id = None
    try:
        async with AsyncSessionLocal() as session, session.begin():
            attack = Attack(
                attacker_id=attacker_id,
                target_id=target_id,
                teacher_id=owned_id,
                status=status,
                resolve_at=datetime.now(UTC),
                next_retry_at=datetime.now(UTC)
                if status is AttackStatus.FAILED
                else None,
                teacher_damage_snapshot=10,
                target_castle_strength_snapshot=100,
                target_defense_power_snapshot=0,
            )
            session.add(attack)
            await session.flush()
            attack_id = attack.id
        async with AsyncSessionLocal() as session:
            with pytest.raises(AttackInProgress):
                await TeacherService().sell(session, attacker_id, owned_id)
            await session.commit()  # Even a caught domain error must leave no writes.
        async with AsyncSessionLocal() as session, session.begin():
            assert await session.get(UserTeacher, owned_id) is not None
            result = await AttackService().resolve_pending_attack(session, attack_id)
            assert result is not None
        async with AsyncSessionLocal() as session, session.begin():
            await TeacherService().sell(session, attacker_id, owned_id)
        async with AsyncSessionLocal() as session:
            assert await session.get(UserTeacher, owned_id) is None
            attack = await session.get(Attack, attack_id)
            assert attack.status is AttackStatus.RESOLVED
            assert attack.teacher_id is None
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(Attack).where(Attack.id == attack_id))
        await _cleanup([attacker_id, target_id])
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(Teacher).where(Teacher.id == teacher_id))
