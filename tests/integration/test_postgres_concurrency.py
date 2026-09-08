import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.enums import ResourceType
from app.db.session import AsyncSessionLocal
from app.db.session import engine
from app.models.mine import Mine
from app.models.daily_quest import DailyQuest, DailyQuestProgress
from app.models.attack import Attack
from app.models.castle import Castle
from app.models.defense import Defense
from app.models.resource import Resource
from app.models.reward import Reward
from app.models.study_pack import StudyPack
from app.models.study_session import StudySession
from app.models.teacher import Teacher
from app.models.user_teacher import UserTeacher
from app.core.enums import AttackStatus, TeacherStatus
from app.services.attack_service import AttackService
from app.models.transaction import Transaction
from app.models.user import User
from app.services.mine_service import MineService
from app.services.reward_service import RewardService, RewardSpec
from app.services.daily_quest_service import DailyQuestService
from app.services.referral_service import ReferralService
from app.services.school_errors import InsufficientCoins
from app.services.study_service import StudyAlreadyActive, StudyService

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
    async with AsyncSessionLocal() as session:
        async with session.begin():
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
        async with AsyncSessionLocal() as session:
            async with session.begin():
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
    async with AsyncSessionLocal() as session:
        async with session.begin():
            mine = Mine(
                user_id=user_id,
                last_collected_at=datetime.now(UTC) - timedelta(minutes=10),
            )
            session.add(mine)

    async def collect() -> tuple[int, int, int]:
        async with AsyncSessionLocal() as session:
            async with session.begin():
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
    async with AsyncSessionLocal() as session:
        async with session.begin():
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
        async with AsyncSessionLocal() as session:
            async with session.begin():
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
    async with AsyncSessionLocal() as session:
        async with session.begin():
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
        async with AsyncSessionLocal() as session:
            async with session.begin():
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
            async with AsyncSessionLocal() as session:
                async with session.begin():
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
        async with AsyncSessionLocal() as session:
            async with session.begin():
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
    async with AsyncSessionLocal() as session:
        async with session.begin():
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
        async with AsyncSessionLocal() as session:
            async with session.begin():
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
