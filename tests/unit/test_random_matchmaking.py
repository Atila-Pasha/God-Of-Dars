from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.attack_service import AttackService
from app.services.resource_service import ResourceService
from app.services.school_errors import TargetProtectedByShield


@pytest.mark.asyncio
async def test_random_rerolls_avoid_recent_opponents_until_pool_is_exhausted() -> None:
    service = AttackService()
    candidates = [2, 3, 4]

    async def pick(_session, *, exclude_target_ids, **_kwargs):
        return next(
            (
                SimpleNamespace(id=user_id)
                for user_id in candidates
                if user_id not in exclude_target_ids
            ),
            None,
        )

    service.users = SimpleNamespace(
        list_active_levels_by_proximity=AsyncMock(return_value=[3]),
        pick_random_active_at_level=AsyncMock(side_effect=pick),
    )
    attacker = SimpleNamespace(id=1, level=3)
    history: tuple[int, ...] = ()
    seen = []
    for _ in range(3):
        target = await service._pick_random_target(
            SimpleNamespace(),
            attacker,
            exclude_target_ids=set(seen[-1:]),
            recent_target_ids=history,
        )
        seen.append(target.id)
        history = (*history, target.id)
    assert seen == [2, 3, 4]

    # With all three seen, an older opponent is allowed but the current one is not.
    target = await service._pick_random_target(
        SimpleNamespace(), attacker, exclude_target_ids={4}, recent_target_ids=history
    )
    assert target.id == 2


@pytest.mark.asyncio
async def test_random_match_prefers_nearby_level_over_unseen_distant_player() -> None:
    service = AttackService()

    async def pick(_session, *, level, exclude_target_ids, **_kwargs):
        candidates = {3: [2, 4], 12: [9]}[level]
        return next(
            (
                SimpleNamespace(id=user_id)
                for user_id in candidates
                if user_id not in exclude_target_ids
            ),
            None,
        )

    service.users = SimpleNamespace(
        list_active_levels_by_proximity=AsyncMock(return_value=[3, 12]),
        pick_random_active_at_level=AsyncMock(side_effect=pick),
    )
    target = await service._pick_random_target(
        SimpleNamespace(),
        SimpleNamespace(id=1, level=3),
        exclude_target_ids={4},
        recent_target_ids=(2, 4),
    )

    assert target.id == 2


@pytest.mark.asyncio
async def test_shielded_live_random_choice_is_replaced_without_paid_reroll() -> None:
    service = AttackService()
    attacker = SimpleNamespace(id=1, level=3, is_active=True)
    selection = SimpleNamespace(
        target_id=2,
        teacher_ids="9",
        recent_target_ids="2",
        version=1,
        reroll_count=1,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    replacement = SimpleNamespace(id=3)
    preview = SimpleNamespace(teacher_ids="9")
    service.users = SimpleNamespace(
        get_by_telegram_user_id=AsyncMock(return_value=attacker),
        get_active_by_id=AsyncMock(return_value=SimpleNamespace(id=2)),
    )
    service._selection_for_update = AsyncMock(return_value=selection)
    service._ensure_no_active_attack = AsyncMock()
    service._preview = AsyncMock(side_effect=TargetProtectedByShield)
    service._find_random_preview = AsyncMock(return_value=(replacement, preview))
    session = SimpleNamespace(flush=AsyncMock())

    result = await service.prepare_random_preview(
        session, attacker_telegram_id=10, teacher_name="افلاطون"
    )

    assert result.preview is preview
    assert selection.target_id == 3
    assert selection.version == 2
    assert selection.reroll_count == 1
    assert selection.recent_target_ids == "2,3"
    service._find_random_preview.assert_awaited_once_with(
        session,
        attacker,
        teacher_name="افلاطون",
        recent_target_ids=(2,),
        exclude_target_ids={2},
    )


@pytest.mark.asyncio
async def test_random_preview_retries_if_candidate_activates_shield() -> None:
    service = AttackService()
    first = SimpleNamespace(id=2)
    second = SimpleNamespace(id=3)
    service._pick_random_target = AsyncMock(side_effect=[first, second])
    preview = SimpleNamespace(target_id=3)
    service._preview = AsyncMock(side_effect=[TargetProtectedByShield(), preview])

    target, result = await service._find_random_preview(
        SimpleNamespace(), SimpleNamespace(id=1), teacher_name="افلاطون"
    )

    assert target is second
    assert result is preview
    assert service._pick_random_target.await_args_list[1].kwargs[
        "exclude_target_ids"
    ] == {2}


@pytest.mark.asyncio
async def test_reroll_of_newly_shielded_opponent_is_free(monkeypatch) -> None:
    service = AttackService()
    attacker = SimpleNamespace(id=1, level=3, is_active=True, resources=object())
    selection = SimpleNamespace(
        target_id=2,
        teacher_ids="9",
        recent_target_ids="2",
        version=1,
        reroll_count=0,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    service.users = SimpleNamespace(
        get_by_telegram_user_id=AsyncMock(return_value=attacker),
        get_active_by_id=AsyncMock(return_value=SimpleNamespace(id=2)),
    )
    service._selection_for_update = AsyncMock(return_value=selection)
    service._ensure_no_active_attack = AsyncMock()
    service._preview_by_teacher_ids = AsyncMock(side_effect=TargetProtectedByShield)
    preview = SimpleNamespace(teacher_ids="9")
    service._find_random_preview = AsyncMock(
        return_value=(SimpleNamespace(id=3), preview)
    )
    debit = AsyncMock()
    monkeypatch.setattr(ResourceService, "debit_coin", debit)
    session = SimpleNamespace(flush=AsyncMock())

    result = await service.reroll_random_preview(
        session, attacker_telegram_id=10, version=1
    )

    assert result.preview is preview
    assert selection.target_id == 3
    assert selection.reroll_count == 0
    debit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reroll_of_attackable_opponent_charges_once(monkeypatch) -> None:
    service = AttackService()
    attacker = SimpleNamespace(id=1, level=3, is_active=True, resources=object())
    selection = SimpleNamespace(
        target_id=2,
        teacher_ids="9",
        recent_target_ids="2",
        version=1,
        reroll_count=0,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    service.users = SimpleNamespace(
        get_by_telegram_user_id=AsyncMock(return_value=attacker),
        get_active_by_id=AsyncMock(return_value=SimpleNamespace(id=2)),
    )
    service._selection_for_update = AsyncMock(return_value=selection)
    service._ensure_no_active_attack = AsyncMock()
    service._preview_by_teacher_ids = AsyncMock(
        return_value=SimpleNamespace(teacher_ids="9")
    )
    service._find_random_preview = AsyncMock(
        return_value=(SimpleNamespace(id=3), SimpleNamespace(teacher_ids="9"))
    )
    debit = AsyncMock()
    monkeypatch.setattr(ResourceService, "debit_coin", debit)
    session = SimpleNamespace(flush=AsyncMock())

    await service.reroll_random_preview(session, attacker_telegram_id=10, version=1)

    debit.assert_awaited_once()
    assert selection.reroll_count == 1
    assert selection.recent_target_ids == "2,3"


@pytest.mark.asyncio
async def test_launched_random_attack_keeps_history_for_next_match() -> None:
    service = AttackService()
    attacker = SimpleNamespace(id=1, is_active=True)
    selection = SimpleNamespace(
        target_id=3,
        teacher_ids="9",
        recent_target_ids="2,3",
        version=4,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    service.users = SimpleNamespace(
        get_by_telegram_user_id=AsyncMock(return_value=attacker)
    )
    service._selection_for_update = AsyncMock(return_value=selection)
    launch = object()
    service.start_attack_by_ids = AsyncMock(return_value=launch)
    session = SimpleNamespace(delete=AsyncMock())

    result = await service.launch_random_attack(
        session, attacker_telegram_id=10, version=4
    )

    assert result is launch
    assert selection.version == 5
    assert selection.expires_at <= datetime.now(UTC)
    assert selection.recent_target_ids == "2,3"
    session.delete.assert_not_awaited()
