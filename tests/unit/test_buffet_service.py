from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.enums import ResourceType
from app.core.game_logic import BuffetConversion
from app.services.buffet_service import BuffetService, InsufficientResource


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "target", "source_amount", "balance", "resource_name"),
    [
        (ResourceType.COIN, ResourceType.DIAMOND, 100, 50, "طلا"),
        (ResourceType.DIAMOND, ResourceType.COIN, 1, 0, "الماس"),
    ],
)
async def test_insufficient_exchange_uses_persian_resource_name(
    source, target, source_amount, balance, resource_name
) -> None:
    conversion = BuffetConversion(
        source=source,
        target=target,
        source_amount=source_amount,
        target_amount=1,
    )
    config = SimpleNamespace(buffet_conversion=Mock(return_value=conversion))
    resources = SimpleNamespace(coin=50, diamond=0)
    setattr(resources, source.value.lower(), balance)
    user_result = Mock(scalar_one_or_none=Mock(return_value=SimpleNamespace(id=1)))
    resource_result = Mock(scalar_one_or_none=Mock(return_value=resources))
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[user_result, resource_result]),
        add_all=Mock(),
        flush=AsyncMock(),
    )

    with pytest.raises(
        InsufficientResource,
        match=f"موجودی {resource_name} برای این تبدیل کافی نیست",
    ):
        await BuffetService(config=config).exchange(
            session,
            1,
            source=source,
            target=target,
            source_amount=source_amount,
        )

    assert resources.coin == 50
    assert resources.diamond == 0
    session.add_all.assert_not_called()
    session.flush.assert_not_awaited()
