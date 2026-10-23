from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.attack_service import AttackService
from app.services.rank_service import RankService
from app.services.resource_service import ResourceService
from app.services.school_errors import RandomOpponentNotFound, TargetProtectedByShield


@pytest.mark.asyncio
async def test_ranked_match_receives_recent_opponents_and_exclusions(
    monkeypatch,
) -> None:
    service = AttackService()
    match = AsyncMock(return_value=SimpleNamespace(id=3))
    monkeypatch.setattr(RankService, "match", match)
    attacker = SimpleNamespace(id=1, level=3)
    session = SimpleNamespace()
    target = await service._pick_random_target(
        session, attacker, exclude_target_ids={4}, recent_target_ids=(2, 4)
    )
    assert target.id == 3
    match.assert_awaited_once_with(session, attacker, excluded={4}, recent=(2, 4))


@pytest.mark.asyncio
async def test_shielded_live_random_choice_is_replaced_without_paid_reroll(
    monkeypatch,
) -> None:
    monkeypatch.setattr(RankService, "assert_available", AsyncMock())
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
async def test_random_preview_retries_if_candidate_activates_shield(
    monkeypatch,
) -> None:
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
async def test_repeated_shield_races_keep_searching_real_players() -> None:
    service = AttackService()
    candidates = [SimpleNamespace(id=index) for index in range(2, 8)]
    preview = SimpleNamespace(target_id=7)
    service._pick_random_target = AsyncMock(side_effect=candidates)
    service._preview = AsyncMock(
        side_effect=[TargetProtectedByShield()] * 5 + [preview]
    )

    target, result = await service._find_random_preview(
        SimpleNamespace(), SimpleNamespace(id=1), teacher_name="افلاطون"
    )

    assert target is candidates[-1] and result is preview
    assert service._pick_random_target.await_args.kwargs["exclude_target_ids"] == {2, 3, 4, 5, 6}


@pytest.mark.asyncio
async def test_reroll_of_newly_shielded_opponent_is_free(monkeypatch) -> None:
    monkeypatch.setattr(RankService, "assert_available", AsyncMock())
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
    monkeypatch.setattr(RankService, "assert_available", AsyncMock())
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
async def test_reroll_keeps_only_real_opponent_without_charging(monkeypatch) -> None:
    monkeypatch.setattr(RankService, "assert_available", AsyncMock())
    service = AttackService()
    attacker = SimpleNamespace(id=1, is_active=True, resources=object())
    selection = SimpleNamespace(
        target_id=2,
        teacher_ids="9",
        recent_target_ids="2",
        version=1,
        reroll_count=0,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    preview = SimpleNamespace(teacher_ids="9")
    service.users = SimpleNamespace(
        get_by_telegram_user_id=AsyncMock(return_value=attacker),
        get_active_by_id=AsyncMock(return_value=SimpleNamespace(id=2)),
    )
    service._selection_for_update = AsyncMock(return_value=selection)
    service._ensure_no_active_attack = AsyncMock()
    service._preview_by_teacher_ids = AsyncMock(return_value=preview)
    service._find_random_preview = AsyncMock(side_effect=RandomOpponentNotFound)
    debit = AsyncMock()
    monkeypatch.setattr(ResourceService, "debit_coin", debit)

    result = await service.reroll_random_preview(
        SimpleNamespace(), attacker_telegram_id=10, version=1
    )

    assert result.preview is preview
    assert selection.target_id == 2 and selection.version == 1
    debit.assert_not_awaited()


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
