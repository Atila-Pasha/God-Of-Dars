from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from admin import handlers, keyboards
from app.core.enums import ResourceType
from app.services.shield_service import ShieldAdminService


@pytest.mark.asyncio
async def test_admin_can_set_or_clear_shield_daily_limit(monkeypatch) -> None:
    monkeypatch.setattr(handlers, "allowed", lambda message: True)
    shield = SimpleNamespace(id=7, name="سپر زنگ تفریح")
    update = AsyncMock(return_value=shield)
    monkeypatch.setattr(handlers.shield_service, "update_shield", update)
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"edit_field": "daily_limit", "edit_id": 7}),
        clear=AsyncMock(),
    )
    message = SimpleNamespace(text="3", answer=AsyncMock())
    session = AsyncMock()

    await handlers.shield_edit_value(message, state, session)
    update.assert_awaited_with(session, 7, daily_limit=3)

    message.text = "-"
    await handlers.shield_edit_value(message, state, session)
    assert update.await_args.kwargs == {"daily_limit": None}

    labels = [row[0].text for row in keyboards.shield_edit_fields(7).inline_keyboard]
    assert "محدودیت روزانه" in labels


def test_admin_rejects_zero_daily_limit() -> None:
    values = {
        "name": "سپر تست",
        "reduction_percent": 0,
        "flat_absorption": 0,
        "purchase_price": 1,
        "unlock_level": 1,
        "duration_minutes": 1,
        "daily_limit": 0,
    }
    values["purchase_resource"] = ResourceType.COIN
    with pytest.raises(ValueError, match="daily_limit"):
        ShieldAdminService._validate(values)
