from types import SimpleNamespace

from app.bot import create_dispatcher
from app.bot.middlewares.group import GroupAccessMiddleware
from app.bot.middlewares.subscription import SubscriptionMiddleware


def test_group_policy_allows_only_stat_and_attack_commands() -> None:
    assert GroupAccessMiddleware._message_is_allowed(
        SimpleNamespace(text="/stat")
    )
    assert GroupAccessMiddleware._message_is_allowed(
        SimpleNamespace(text="/attack@my_bot")
    )
    assert not GroupAccessMiddleware._message_is_allowed(
        SimpleNamespace(text="/profile")
    )
    assert not GroupAccessMiddleware._message_is_allowed(
        SimpleNamespace(text="پروفایل")
    )


def test_group_policy_allows_plain_text_for_question_answers() -> None:
    assert GroupAccessMiddleware._message_is_allowed(
        SimpleNamespace(text="تهران")
    )


def test_group_policy_runs_before_subscription_middleware() -> None:
    dispatcher = create_dispatcher()

    middlewares = list(dispatcher.message.outer_middleware)
    assert isinstance(middlewares[0], GroupAccessMiddleware)
    assert isinstance(middlewares[1], SubscriptionMiddleware)
