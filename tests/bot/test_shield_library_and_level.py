from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.library import _shield_library_text
from app.core.enums import ResourceType
from app.services.shield_service import ShieldService


@pytest.mark.asyncio
async def test_shield_shop_catalog_filters_by_player_level() -> None:
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
    session = SimpleNamespace(execute=AsyncMock(return_value=result))

    await ShieldService().catalog(session, player_level=5)
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "shields.unlock_level <= 5" in sql

    await ShieldService().catalog(session, player_level=None)
    all_statement = session.execute.await_args.args[0]
    all_sql = str(all_statement.compile(compile_kwargs={"literal_binds": True}))
    assert "shields.unlock_level <=" not in all_sql


def test_shield_library_shows_full_details_with_custom_emoji() -> None:
    shield = SimpleNamespace(
        name="سپر زنگ تفریح",
        purchase_resource=ResourceType.COIN,
        purchase_price=120,
        unlock_level=1,
        duration_minutes=30,
        description="محافظت کامل",
    )
    text = _shield_library_text([shield])

    assert "tg://emoji?id=5825861861278490879" in text
    assert "120 طلا" in text
    assert "30 دقیقه" in text
    assert "محافظت کامل" in text
