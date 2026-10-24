import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.methods import SendMessage

from admin import broadcast, handlers, keyboards
from app.models.broadcast_job import BroadcastJob


@pytest.mark.asyncio
async def test_broadcast_retries_telegram_rate_limit_without_losing_recipient(
    monkeypatch,
) -> None:
    job = BroadcastJob(id=9, text="خبر")
    bot = SimpleNamespace(
        send_message=AsyncMock(
            side_effect=[
                TelegramRetryAfter(
                    method=SendMessage(chat_id=123, text="خبر"),
                    message="Flood control",
                    retry_after=2,
                ),
                None,
            ]
        )
    )
    pause = AsyncMock()
    monkeypatch.setattr(broadcast, "_pause", pause)

    await broadcast._send_one(bot, job, 123, asyncio.Event())

    assert bot.send_message.await_count == 2
    pause.assert_awaited_once()
    assert pause.await_args.args[0] >= 2


@pytest.mark.asyncio
async def test_broadcast_retries_temporary_network_error(monkeypatch) -> None:
    job = BroadcastJob(id=10, text="خبر")
    bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=[OSError("offline"), None])
    )
    pause = AsyncMock()
    monkeypatch.setattr(broadcast, "_pause", pause)

    await broadcast._send_one(bot, job, 123, asyncio.Event())

    assert bot.send_message.await_count == 2
    pause.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcast_handler_queues_job_without_sending(monkeypatch) -> None:
    monkeypatch.setattr(handlers, "allowed", lambda _: True)
    job = None

    async def commit() -> None:
        if job is not None:
            job.id = 77

    def add(item: BroadcastJob) -> None:
        nonlocal job
        job = item

    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(one=lambda: (900, 500))),
        add=Mock(side_effect=add),
        commit=AsyncMock(side_effect=commit),
    )
    message = SimpleNamespace(
        text="سلام به همه",
        photo=None,
        caption=None,
        chat=SimpleNamespace(id=123),
        answer=AsyncMock(),
    )
    state = SimpleNamespace(clear=AsyncMock())

    await handlers.broadcast_send(message, state, session)

    assert job is not None
    assert (job.admin_chat_id, job.max_user_id, job.total, job.text) == (
        123,
        900,
        500,
        "سلام به همه",
    )
    session.commit.assert_awaited_once()
    state.clear.assert_awaited_once()
    assert "شناسه 77" in message.answer.await_args.args[0]
    assert "📊 وضعیت پیام همگانی" in [
        button.text for row in keyboards.publishing_menu().keyboard for button in row
    ]


@pytest.mark.asyncio
async def test_broadcast_worker_persists_progress_and_sends_final_report(
    monkeypatch,
) -> None:
    job = BroadcastJob(
        id=3,
        admin_chat_id=777,
        status="PENDING",
        text="خبر",
        max_user_id=20,
        total=2,
        last_user_id=0,
        sent=0,
        failed=0,
    )
    users = [(10, 101), (20, 102)]

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _model, _id, **_kwargs):
            return job

        async def execute(self, _query):
            return SimpleNamespace(
                all=lambda: [row for row in users if row[0] > job.last_user_id]
            )

        async def scalar(self, _query):
            return (
                job
                if job.status == "COMPLETED" and job.report_sent_at is None
                else None
            )

        async def commit(self):
            return None

    monkeypatch.setattr(broadcast, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(broadcast.settings, "TELEGRAM_SEND_DELAY", 0)

    async def send_message(*, chat_id: int, text: str):
        if chat_id == 102:
            raise TelegramBadRequest(
                method=SendMessage(chat_id=102, text=text),
                message="chat not found",
            )

    main_bot = SimpleNamespace(send_message=AsyncMock(side_effect=send_message))
    admin_bot = SimpleNamespace(send_message=AsyncMock())
    stop_event = asyncio.Event()

    await broadcast._process_page(main_bot, job.id, stop_event)
    assert (job.status, job.last_user_id, job.sent, job.failed) == (
        "RUNNING",
        20,
        1,
        1,
    )
    await broadcast._process_page(main_bot, job.id, stop_event)
    assert job.status == "COMPLETED"
    assert await broadcast._send_pending_report(admin_bot) is True
    assert job.report_sent_at is not None
    assert "موفق: 1" in admin_bot.send_message.await_args.kwargs["text"]
    assert "ناموفق: 1" in admin_bot.send_message.await_args.kwargs["text"]
    assert await broadcast._send_pending_report(admin_bot) is False
