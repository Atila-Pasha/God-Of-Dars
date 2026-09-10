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
            await session.execute(delete(Transaction).where(Transaction.user_id.in_(user_ids)))
            await session.execute(delete(Reward).where(Reward.user_id.in_(user_ids)))
            await session.execute(
                delete(Notification).where(Notification.recipient_user_id.in_(user_ids))
            )
            await session.execute(delete(User).where(User.id.in_(user_ids)))
            if pack_key is not None:
                await session.execute(delete(StudyPack).where(StudyPack.key == pack_key))


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
            assert await session.scalar(
                select(Resource.coin).where(Resource.user_id == user_id)
            ) == 7
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
                select(func.count(StudySession.id))
                .where(
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
            assert await session.scalar(
                select(Resource.coin).where(Resource.user_id == referrer_id)
            ) == 3
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
            await session.execute(
                delete(DailyQuest).where(DailyQuest.id == quest_id)
            )
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
            assert await session.scalar(
                select(func.count(Transaction.id)).where(
                    Transaction.reference_type == "ATTACK",
                    Transaction.reference_id == attack_id,
                )
            ) == 3
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(delete(Attack).where(Attack.id == attack_id))
                await session.execute(delete(Transaction).where(Transaction.user_id.in_([attacker_id, target_id])))
                await session.execute(delete(User).where(User.id.in_([attacker_id, target_id])))
                if teacher_id is not None:
                    await session.execute(delete(Teacher).where(Teacher.id == teacher_id))


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
                    processing_at=datetime.now(UTC) if status is AttackStatus.PROCESSING else None,
                    failed_at=datetime.now(UTC) if status is AttackStatus.FAILED else None,
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
                                    select(User.telegram_user_id).where(User.id == attacker_id)
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
                                select(User.telegram_user_id).where(User.id == attacker_id)
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
                await session.execute(delete(User).where(User.id.in_([attacker_id, target_id])))
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
                await session.execute(delete(Attack).where(Attack.attacker_id == attacker_id))
                await session.execute(delete(Transaction).where(Transaction.user_id.in_([attacker_id, target_id])))
                await session.execute(delete(User).where(User.id.in_([attacker_id, target_id])))
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
                    delete(Attack).where(
                        Attack.attacker_id.in_([first_id, second_id])
                    )
                )
                await session.execute(
                    delete(Transaction).where(
                        Transaction.user_id.in_([first_id, second_id])
                    )
                )
                await session.execute(delete(User).where(User.id.in_([first_id, second_id])))
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

    async def receive_and_pause(session, user_id, incoming_damage):
        result = await original_receive(session, user_id, incoming_damage)
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
                await session.execute(delete(Transaction).where(Transaction.user_id.in_([attacker_id, target_id])))
                await session.execute(delete(Reward).where(Reward.user_id.in_([attacker_id, target_id])))
                await session.execute(delete(User).where(User.id.in_([attacker_id, target_id])))
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
                        "UPDATE resources SET coin = coin + 1 "
                        "WHERE user_id = :user_id"
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
async def test_stale_processing_attack_recovers_without_duplicate_ledger() -> None:
    attacker_id = await _user()
    target_id = await _user(coin=10)
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
            assert await session.scalar(
                select(func.count(Transaction.id)).where(
                    Transaction.reference_type == "ATTACK",
                    Transaction.reference_id == attack_id,
                )
            ) == 3
            assert await session.scalar(
                select(func.count(Notification.id)).where(
                    Notification.idempotency_key.like(f"ATTACK_RESULT:{attack_id}:%")
                )
            ) == 2
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(delete(Attack).where(Attack.id == attack_id))
                await session.execute(delete(Transaction).where(Transaction.user_id.in_([attacker_id, target_id])))
                await session.execute(delete(User).where(User.id.in_([attacker_id, target_id])))
                await session.execute(delete(Teacher).where(Teacher.id == teacher_id))


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
            process_due_notifications(bot, batch_size=1),
            process_due_notifications(bot, batch_size=1),
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
        await process_due_notifications(bot, batch_size=1)
        async with AsyncSessionLocal() as session, session.begin():
            row = await session.scalar(
                select(Notification)
                .where(Notification.idempotency_key == "TEST:notification:retry")
                .with_for_update()
            )
            row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await process_due_notifications(bot, batch_size=1)
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
        await process_due_notifications(bot, batch_size=1)
        async with AsyncSessionLocal() as session, session.begin():
            row = await session.scalar(
                select(Notification)
                .where(
                    Notification.idempotency_key
                    == "TEST:notification:crash-window"
                )
                .with_for_update()
            )
            row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await process_due_notifications(bot, batch_size=1)
        assert len(deliveries) == 2
    finally:
        await _cleanup([user_id])


@pytest.mark.asyncio
async def test_stale_processing_notification_is_recovered_after_worker_restart() -> None:
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
        await process_due_notifications(bot, batch_size=1)
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
async def test_shield_activation_and_attack_resolution_are_serializable() -> None:
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
        results = await asyncio.gather(resolve(), activate(), return_exceptions=True)
        assert not [result for result in results if isinstance(result, Exception)]
        async with AsyncSessionLocal() as session:
            attack = await session.get(Attack, attack_id)
            assert attack.status is AttackStatus.RESOLVED
            castle_strength = await session.scalar(
                select(Castle.strength).where(Castle.user_id == target_id)
            )
            assert 0 <= castle_strength <= 100
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
                await session.execute(delete(Transaction).where(Transaction.user_id.in_([attacker_id, target_id])))
                await session.execute(delete(User).where(User.id.in_([attacker_id, target_id])))
                await session.execute(delete(Shield).where(Shield.id == shield_id))
                await session.execute(delete(Teacher).where(Teacher.id == teacher_id))
