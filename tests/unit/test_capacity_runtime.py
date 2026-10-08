import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.storage.base import StorageKey

from app.bot.isolation import UserEventIsolation
from app.services.subscription_service import SubscriptionService


@pytest.mark.asyncio
async def test_user_serialization_across_chats_and_cancelled_waiter_cleanup():
    isolation = UserEventIsolation()
    key = StorageKey(bot_id=1, chat_id=1, user_id=5)
    other_chat = StorageKey(bot_id=1, chat_id=2, user_id=5)
    order = []

    async def waiting():
        async with isolation.lock(other_chat):
            order.append("waiter")

    async with isolation.lock(key):
        waiter = asyncio.create_task(waiting())
        cancelled = asyncio.create_task(waiting())
        await asyncio.sleep(0)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        assert not order
        async with isolation.lock(StorageKey(bot_id=1, chat_id=1, user_id=6)):
            order.append("different user")
    await waiter
    assert order == ["different user", "waiter"]
    assert isolation._entries == {}


@pytest.mark.asyncio
async def test_membership_burst_is_coalesced_and_cache_evicts_only_one():
    service = SubscriptionService(["@channel"])
    service.membership_cache_max_entries = 2

    async def member(**kwargs):
        await asyncio.sleep(0.01)
        return SimpleNamespace(status="member")

    bot = SimpleNamespace(token="test", get_chat_member=AsyncMock(side_effect=member))
    assert all(await asyncio.gather(*(service.is_member(bot, 1) for _ in range(50))))
    assert bot.get_chat_member.await_count == 1
    await service.is_member(bot, 2)
    await service.is_member(bot, 3)
    assert len(service._membership_cache) == 2
    await service.is_member(bot, 2)
    assert bot.get_chat_member.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role, attacks, notifications, cleanup",
    [
        ("combined", 2, 3, 1),
        ("bot", 0, 3, 1),
        ("attacks", 2, 0, 0),
    ],
)
async def test_runtime_roles_do_not_duplicate_pollers_or_senders(
    monkeypatch, role, attacks, notifications, cleanup
):
    from app.workers import runtime

    monkeypatch.setattr(runtime.settings, "RUNTIME_ROLE", role)
    monkeypatch.setattr(runtime.settings, "WORKER_COUNT", 2)
    monkeypatch.setattr(runtime.settings, "NOTIFICATION_WORKER_COUNT", 3)
    attack = AsyncMock()
    notification = AsyncMock()
    clean = AsyncMock()
    monkeypatch.setattr(runtime, "_attack_worker", attack)
    monkeypatch.setattr(runtime, "run_notification_worker", notification)
    monkeypatch.setattr(runtime, "run_game_message_cleanup_worker", clean)
    await runtime.run_workers(SimpleNamespace())
    assert attack.await_count == attacks
    assert notification.await_count == notifications
    assert clean.await_count == cleanup


@pytest.mark.asyncio
async def test_shutdown_drains_and_cancels_stuck_updates():
    from app.bot.shutdown import drain_updates

    completed = asyncio.create_task(asyncio.sleep(0))
    stuck = asyncio.create_task(asyncio.Event().wait())
    dispatcher = SimpleNamespace(_handle_update_tasks={completed, stuck})
    await drain_updates(dispatcher, timeout=0.01)
    assert completed.done() and not completed.cancelled()
    assert stuck.cancelled()


@pytest.mark.asyncio
async def test_long_polling_bypasses_saturated_outgoing_slots(monkeypatch):
    from aiogram import Bot
    from aiogram.methods import GetUpdates

    from app.bot import custom_emojis

    custom_emojis.install()
    monkeypatch.setattr(custom_emojis, "_telegram_api_semaphore", asyncio.Semaphore(0))
    transport = AsyncMock(return_value=[])
    bot = Bot("123456:TEST", session=transport)
    assert await asyncio.wait_for(bot(GetUpdates()), timeout=0.5) == []
    transport.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("processed, expected_delay", [(4, 0), (0, 2.0)])
async def test_notification_workers_only_idle_when_queue_is_not_full(
    monkeypatch, processed, expected_delay
):
    from app.workers import notification_worker as worker

    monkeypatch.setattr(worker.settings, "WORKER_BATCH_SIZE", 4)
    monkeypatch.setattr(worker.settings, "WORKER_POLL_INTERVAL", 2.0)
    monkeypatch.setattr(
        worker, "process_due_notifications", AsyncMock(return_value=processed)
    )
    sleep = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(worker.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await worker.run_notification_worker(SimpleNamespace())
    sleep.assert_awaited_once_with(expected_delay)
