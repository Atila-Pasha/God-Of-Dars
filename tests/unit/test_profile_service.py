from types import SimpleNamespace

import pytest

from app.repositories.profile import ProfileSnapshot
from app.services.profile_service import ProfileNotFound, ProfileService


def snapshot() -> ProfileSnapshot:
    return ProfileSnapshot(
        user=SimpleNamespace(id=7),
        teachers_count=3,
        active_teachers_count=2,
        attacks_sent=10,
        successful_attacks=6,
        pending_attacks=1,
        attacks_received=4,
        damage_dealt=120,
        loot_coin=80,
        loot_diamond=5,
        loot_banana=2,
        answers_count=8,
        correct_answers=6,
        referrals_count=3,
    )


@pytest.mark.asyncio
async def test_profile_service_returns_repository_snapshot() -> None:
    repository = SimpleNamespace(get_snapshot=lambda session, user_id: None)

    async def get_snapshot(session, user_id):
        return snapshot()

    repository.get_snapshot = get_snapshot
    service = ProfileService(repository)

    result = await service.snapshot(SimpleNamespace(), 7)

    assert result.user.id == 7
    assert result.successful_attacks == 6


@pytest.mark.asyncio
async def test_profile_service_rejects_unknown_user() -> None:
    async def get_snapshot(session, user_id):
        return None

    service = ProfileService(SimpleNamespace(get_snapshot=get_snapshot))

    with pytest.raises(ProfileNotFound):
        await service.snapshot(SimpleNamespace(), 99)
