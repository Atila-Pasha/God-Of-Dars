from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.callbacks import MineCallback
from app.bot.handlers import mine
from app.services.school_errors import InsufficientDiamonds


@pytest.mark.asyncio
async def test_mine_upgrade_reports_insufficient_diamonds(monkeypatch) -> None:
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )
    monkeypatch.setattr(
        mine.user_service,
        "get_active_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(id=7)),
    )
    monkeypatch.setattr(
        mine.mine_service,
        "upgrade",
        AsyncMock(side_effect=InsufficientDiamonds),
    )

    await mine.mine_callback(
        callback, MineCallback(action="confirm_upgrade"), AsyncMock()
    )

    callback.answer.assert_awaited_once_with(
        "الماس کافی برای ارتقای معدن ندارید.", show_alert=True
    )
