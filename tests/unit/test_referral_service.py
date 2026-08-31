from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.enums import ResourceType
from app.models.user import User
from app.services.referral_service import (
    ReferralAlreadySet,
    ReferralCycle,
    ReferralService,
    ReferrerNotFound,
    SelfReferral,
)


class FakeReferralRepository:
    def __init__(self, referred: User, referrer: User | None):
        self.users = {referred.id: referred}
        if referrer is not None:
            self.users[referrer.id] = referrer
        self.locked_ids = []

    async def get_user_for_update(self, session, user_id):
        self.locked_ids.append(user_id)
        return self.users.get(user_id)

    async def count_referrals(self, session, referrer_id):
        return sum(user.referrer_id == referrer_id for user in self.users.values())

    async def list_referrals(self, session, referrer_id):
        return [user for user in self.users.values() if user.referrer_id == referrer_id]

    async def is_descendant(self, session, *, ancestor_id, descendant_id):
        current = self.users.get(descendant_id)
        seen = set()
        while current is not None and current.referrer_id not in seen:
            if current.referrer_id == ancestor_id:
                return True
            seen.add(current.referrer_id)
            current = self.users.get(current.referrer_id)
        return False


def user(user_id: int, *, referrer_id: int | None = None) -> User:
    return User(
        id=user_id,
        telegram_user_id=user_id + 1000,
        first_name=f"user-{user_id}",
        is_active=True,
        referrer_id=referrer_id,
    )


def session():
    return SimpleNamespace(flush=AsyncMock())


def test_referral_payload_is_strict_and_round_trips():
    assert ReferralService.payload_for(42) == "ref_42"
    assert ReferralService.parse_payload("ref_42") == 42
    assert ReferralService.parse_payload(" ref_42 ") == 42
    assert ReferralService.parse_payload("ref_0") is None
    assert ReferralService.parse_payload("ref_bad") is None


@pytest.mark.asyncio
async def test_referral_is_applied_once_and_locks_users_deterministically():
    referred = user(20)
    referrer = user(10)
    repository = FakeReferralRepository(referred, referrer)
    reward_service = AsyncMock()
    reward_service.grant.return_value = None
    service = ReferralService(repository, reward_service=reward_service)

    result = await service.apply(
        session(), referred_user_id=referred.id, referrer_id=referrer.id
    )

    assert result.applied is True
    assert referred.referrer_id == referrer.id
    assert repository.locked_ids == [10, 20]
    assert reward_service.grant.await_count == 2
    inviter_reward_call = reward_service.grant.await_args_list[0]
    assert inviter_reward_call.kwargs["spec"].resource_type is ResourceType.DIAMOND
    assert inviter_reward_call.kwargs["spec"].amount == 10

    repeated = await service.apply(
        session(), referred_user_id=referred.id, referrer_id=referrer.id
    )
    assert repeated.applied is False
    assert reward_service.grant.await_count == 2


@pytest.mark.asyncio
async def test_self_referral_and_unknown_referrer_are_rejected():
    repository = FakeReferralRepository(user(10), None)
    service = ReferralService(repository)

    with pytest.raises(SelfReferral):
        await service.apply(session(), referred_user_id=10, referrer_id=10)
    with pytest.raises(ReferrerNotFound):
        await service.apply(session(), referred_user_id=10, referrer_id=99)


@pytest.mark.asyncio
async def test_different_referrer_cannot_replace_existing_attribution():
    referred = user(20, referrer_id=10)
    repository = FakeReferralRepository(referred, user(30))
    service = ReferralService(repository)

    with pytest.raises(ReferralAlreadySet):
        await service.apply(session(), referred_user_id=20, referrer_id=30)


@pytest.mark.asyncio
async def test_referral_cycle_is_rejected():
    referred = user(20)
    referrer = user(10, referrer_id=20)
    repository = FakeReferralRepository(referred, referrer)
    service = ReferralService(repository)

    with pytest.raises(ReferralCycle):
        await service.apply(session(), referred_user_id=20, referrer_id=10)
