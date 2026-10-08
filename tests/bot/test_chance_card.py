from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.callbacks_chance import (
    ChanceBoxCallback,
    ChanceBoxCaptchaCallback,
    ChanceCardCallback,
)
from app.bot.chance_banners import chance_box_winner_banner
from app.bot.handlers import chance
from app.core.enums import ResourceType
from app.services.chance_service import WrongCaptcha


@pytest.mark.asyncio
async def test_claimed_box_posts_winner_banner_and_deletes_the_box(monkeypatch) -> None:
    monkeypatch.setattr(chance, "Message", SimpleNamespace)
    box = SimpleNamespace(
        amount=100,
        resource_type=ResourceType.DIAMOND,
        telegram_message_id=700,
        sticker_message_id=699,
    )
    monkeypatch.setattr(
        chance.chance_service, "claim_box", AsyncMock(return_value=(box, True))
    )
    group_message = SimpleNamespace(
        message_id=700,
        chat=SimpleNamespace(id=-123),
        answer=AsyncMock(),
    )
    bot = SimpleNamespace(delete_message=AsyncMock())
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=42, first_name="AtilA", last_name=None),
        message=group_message,
        bot=bot,
        answer=AsyncMock(),
    )
    session = SimpleNamespace(commit=AsyncMock())

    await chance.claim_box(callback, ChanceBoxCallback(box_id=3), session)

    text = group_message.answer.await_args.args[0]
    assert "tg://emoji?id=5915892656499597169" in text
    assert "tg://emoji?id=5825709849500985213" in text
    assert "tg://emoji?id=5235470399730361615" in text
    assert "پاسخ صحیح داده شد" in text
    assert "فرمانده « AtilA » زودتر از همه پاسخ داد و جعبه شانس را باز کرد" in text
    assert "100" not in text
    assert "الماس" not in text
    callback.answer.assert_awaited_once_with(
        "آفرین! 100 الماس دریافت کردی.", show_alert=True
    )
    assert bot.delete_message.await_count == 2
    bot.delete_message.assert_any_await(chat_id=-123, message_id=700)
    bot.delete_message.assert_any_await(chat_id=-123, message_id=699)
    assert box.telegram_message_id is None
    assert box.sticker_message_id is None
    assert session.commit.await_count == 2


def test_box_winner_banner_names_player_without_revealing_reward() -> None:
    text = chance_box_winner_banner("AtilA")

    assert "📝" in text and "✔️" in text and "⬅️" in text
    assert "« AtilA »" in text
    assert "جعبه شانس را باز کرد" in text
    assert "دریافت کرد" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("resource", "label"),
    [
        (ResourceType.COIN, "سکه طلا"),
        (ResourceType.DIAMOND, "الماس"),
        (ResourceType.BANANA, "موز"),
    ],
)
async def test_box_reward_is_shown_only_in_winner_alert(
    monkeypatch, resource, label
) -> None:
    monkeypatch.setattr(chance, "Message", SimpleNamespace)
    box = SimpleNamespace(
        amount=100,
        resource_type=resource,
        telegram_message_id=700,
        sticker_message_id=None,
    )
    monkeypatch.setattr(
        chance.chance_service, "claim_box", AsyncMock(return_value=(box, True))
    )
    message = SimpleNamespace(
        message_id=700,
        chat=SimpleNamespace(id=-123),
        answer=AsyncMock(),
    )
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=42, first_name="AtilA", last_name=None),
        message=message,
        bot=SimpleNamespace(delete_message=AsyncMock()),
        answer=AsyncMock(),
    )

    await chance.claim_box(
        callback, ChanceBoxCallback(box_id=3), SimpleNamespace(commit=AsyncMock())
    )

    callback.answer.assert_awaited_once_with(
        f"آفرین! 100 {label} دریافت کردی.", show_alert=True
    )
    assert "100" not in message.answer.await_args.args[0]
    assert label not in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_wrong_box_choice_only_alerts_its_player(monkeypatch) -> None:
    monkeypatch.setattr(
        chance.chance_service, "claim_box", AsyncMock(side_effect=WrongCaptcha)
    )
    message = SimpleNamespace(answer=AsyncMock(), delete=AsyncMock())
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=42), message=message, answer=AsyncMock()
    )
    session = SimpleNamespace(commit=AsyncMock())

    await chance.claim_box(
        callback, ChanceBoxCaptchaCallback(box_id=3, answer="ACEX"), session
    )

    chance.chance_service.claim_box.assert_awaited_once_with(session, 3, 42, "ACEX")
    session.commit.assert_awaited_once()
    assert "فقط یک فرصت" in callback.answer.await_args.args[0]
    message.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrong_math_answer_ends_card_flow_after_one_attempt(monkeypatch) -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        text="22",
        answer=AsyncMock(),
    )
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"card_id": 7}), clear=AsyncMock()
    )
    session = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(
        chance.user_service,
        "get_active_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(id=5)),
    )
    monkeypatch.setattr(
        chance.chance_service,
        "claim_card",
        AsyncMock(side_effect=WrongCaptcha),
    )

    await chance.verify_card(message, state, session)

    session.commit.assert_awaited_once()
    state.clear.assert_awaited_once()
    assert "فقط یک فرصت" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_used_card_button_does_not_prompt_for_another_answer(monkeypatch) -> None:
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
    )
    state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(user_id=5, is_claimed=True))
    )
    monkeypatch.setattr(
        chance.user_service,
        "get_active_by_telegram_user_id",
        AsyncMock(return_value=SimpleNamespace(id=5)),
    )

    await chance.start_card(callback, ChanceCardCallback(card_id=7), state, session)

    assert "قابل استفاده نیست" in callback.answer.await_args.args[0]
    state.set_state.assert_not_awaited()
    callback.message.answer.assert_not_awaited()
