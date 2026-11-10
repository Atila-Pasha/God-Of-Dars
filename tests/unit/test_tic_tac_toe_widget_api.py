import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.bot import custom_emojis
from app.bot.tic_tac_toe_widget import widget_api


class FakeResponse:
    def __init__(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def json(self, **_kwargs):
        return self.payload


@pytest.mark.asyncio
async def test_widget_api_shares_bot_limit_and_retries_rate_limit(monkeypatch) -> None:
    gate = asyncio.Semaphore(0)
    monkeypatch.setattr(custom_emojis, "_telegram_api_semaphore", gate)
    responses = iter(
        (
            FakeResponse(429, {"ok": False, "parameters": {"retry_after": 0}}),
            FakeResponse(200, {"ok": True, "result": {"message_id": 12}}),
        )
    )
    session = SimpleNamespace(
        post=Mock(side_effect=lambda *_args, **_kwargs: next(responses))
    )
    bot = SimpleNamespace(
        token="123:test",
        session=SimpleNamespace(
            create_session=AsyncMock(return_value=session),
            api=SimpleNamespace(
                api_url=lambda *, token, method: (
                    f"https://api.telegram.org/bot{token}/{method}"
                )
            ),
        ),
    )
    task = asyncio.create_task(widget_api(bot, "sendWidget", {"chat_id": 1}))
    await asyncio.sleep(0)
    session.post.assert_not_called()
    gate.release()
    assert (await task)["result"]["message_id"] == 12
    assert session.post.call_count == 2
    assert (
        session.post.call_args.args[0]
        == "https://api.telegram.org/bot123:test/sendWidget"
    )
