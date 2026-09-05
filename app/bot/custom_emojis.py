from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import MessageEntity

# The visible character is retained as a fallback. Telegram replaces it with
# the custom emoji when the entity is present, while old clients still see a
# normal emoji.
CUSTOM_EMOJI_IDS: dict[str, str] = {
    "🍌": "5825496299432058457",
    "💎": "5825753314570018832",
    "🎁": "5825832256068918886",
    "💌": "5825447362574688486",
    "🏆": "5823430604846276719",
    "🏰": "5823403314624080082",
    "📜": "5825898080737697438",
    "🪙": "5825656871079387950",
    "🏥": "5825570280243732195",
    "📚": "5825629907274703191",
    "📌": "5825898080737697438",
    "🍽": "5823511728188563725",
    "⭐": "5825647731388981287",
    "🌟": "5825647731388981287",
    "🏫": "5825697157872623308",
    "⚔️": "5825697157872623308",
    "📢": "5825791209066471425",
    "🧭": "5823443584237444682",
    "✨": "5825920844064366385",
    "🏅": "5823282613158158030",
    "✅": "5825709849500985213",
    "❌": "5825504038963125908",
    "🗡️": "5823192436024813346",
    # UI aliases: every remaining visual emoji used by the bot is mapped to
    # one of the supplied premium emoji packs as well.
    "⛏": "5823474022670671455",
    "⛏️": "5823474022670671455",
    "👨‍🏫": "5825697157872623308",
    "👤": "5823282613158158030",
    "🛡": "5823403314624080082",
    "⚙️": "5823443584237444682",
    "📅": "5825898080737697438",
    "❓": "5825898080737697438",
    "✍️": "5825629907274703191",
    "🔙": "5823443584237444682",
    "⬆️": "5825647731388981287",
    "🛒": "5825656871079387950",
    "💰": "5825656871079387950",
    "🩹": "5825570280243732195",
    "❤️": "5825570280243732195",
    "🏗️": "5825697157872623308",
    "🪑": "5825697157872623308",
    "🎖": "5823282613158158030",
    "📊": "5825920844064366385",
    "⚡": "5823192436024813346",
    "🔄": "5823443584237444682",
    "📣": "5825791209066471425",
    "🃏": "5825447362574688486",
    "⏳": "5823443584237444682",
    "⏱️": "5823443584237444682",
    "🎯": "5823192436024813346",
    "💥": "5823192436024813346",
    "🤝": "5823282613158158030",
    "📎": "5825898080737697438",
    "🧙": "5825647731388981287",
    "🟢": "5825709849500985213",
    "🟠": "5825647731388981287",
    "🔴": "5825504038963125908",
    "🔵": "5823443584237444682",
    "🍽️": "5823511728188563725",
    "⏰": "5823443584237444682",
    "⚪": "5825647731388981287",
    "⛔": "5825504038963125908",
    "✏️": "5825629907274703191",
    "🆔": "5825898080737697438",
    "🌱": "5825697157872623308",
    "🎉": "5823430604846276719",
    "🏯": "5823403314624080082",
    "👑": "5823430604846276719",
    "👥": "5823282613158158030",
    "📈": "5825920844064366385",
    "📖": "5825629907274703191",
    "📤": "5825791209066471425",
    "📦": "5825832256068918886",
    "📱": "5825898080737697438",
    "🔒": "5823403314624080082",
    "🔗": "5823443584237444682",
    "🗑": "5825504038963125908",
    "😁": "5825647731388981287",
}

# Set by the group middleware while a group update is being handled. This
# lets every outgoing response in that handler reply to the triggering message
# without changing every individual handler call site.
_group_reply_context: ContextVar[tuple[int, int] | None] = ContextVar(
    "godofdars_group_reply_context", default=None
)


def set_group_reply_context(chat_id: int, message_id: int):
    return _group_reply_context.set((chat_id, message_id))


def reset_group_reply_context(token) -> None:
    _group_reply_context.reset(token)


def _add_group_reply(kwargs: dict[str, Any]) -> None:
    context = _group_reply_context.get()
    if context is None or kwargs.get("reply_to_message_id") is not None:
        return
    chat_id = kwargs.get("chat_id")
    if chat_id == context[0]:
        kwargs["reply_to_message_id"] = context[1]


def premium_emoji_id(value: str | None, *, fallback: str | None = None) -> str | None:
    """Return a Telegram custom-emoji id from an admin-stored value or alias."""
    if value and value.isdigit():
        return value
    if value:
        return CUSTOM_EMOJI_IDS.get(value)
    return CUSTOM_EMOJI_IDS.get(fallback) if fallback else None


def custom_emoji_entity(
    value: str | None, *, fallback: str
) -> tuple[str, MessageEntity | None]:
    """Return visible fallback text and an entity for a stored custom emoji."""
    visible = value if value and not value.isdigit() else fallback
    emoji_id = premium_emoji_id(value)
    if emoji_id is None:
        return visible, None
    return visible, MessageEntity(
        type="custom_emoji",
        offset=0,
        length=len(visible.encode("utf-16-le")) // 2,
        custom_emoji_id=emoji_id,
    )


def strip_custom_emoji_fallbacks(text: str) -> str:
    """Remove textual fallback emojis when a button has a premium icon slot."""
    for source in sorted(CUSTOM_EMOJI_IDS, key=len, reverse=True):
        text = text.replace(source, "")
    return " ".join(text.split())


def custom_emoji_entities(text: str) -> list[MessageEntity]:
    """Build Telegram custom-emoji entities using UTF-16 offsets."""
    entities: list[MessageEntity] = []
    sources = sorted(CUSTOM_EMOJI_IDS, key=len, reverse=True)
    index = 0
    while index < len(text):
        source = next((item for item in sources if text.startswith(item, index)), None)
        if source is None:
            index += 1
            continue
        offset = len(text[:index].encode("utf-16-le")) // 2
        length = len(source.encode("utf-16-le")) // 2
        entities.append(
            MessageEntity(
                type="custom_emoji",
                offset=offset,
                length=length,
                custom_emoji_id=CUSTOM_EMOJI_IDS[source],
            )
        )
        index += len(source)
    return entities


def _decorate(kwargs: dict[str, Any], text_key: str, entities_key: str) -> None:
    text = kwargs.get(text_key)
    if not isinstance(text, str):
        return
    generated = custom_emoji_entities(text)
    if not generated:
        return
    existing = kwargs.get(entities_key)
    if not existing:
        kwargs[entities_key] = generated


def _decorate_method(method: Any) -> None:
    """Decorate aiogram method objects used by Message.answer/edit shortcuts."""
    context = _group_reply_context.get()
    if (
        context is not None
        and getattr(method, "chat_id", None) == context[0]
        and getattr(method, "reply_to_message_id", None) is None
        and hasattr(method, "reply_to_message_id")
    ):
        method.reply_to_message_id = context[1]
    if hasattr(method, "text") and isinstance(method.text, str):
        generated = custom_emoji_entities(method.text)
        if generated and not getattr(method, "entities", None):
            method.entities = generated
    if hasattr(method, "caption") and isinstance(method.caption, str):
        generated = custom_emoji_entities(method.caption)
        if generated and not getattr(method, "caption_entities", None):
            method.caption_entities = generated
    markup = getattr(method, "reply_markup", None)
    if markup is not None:
        _decorate_markup({"reply_markup": markup})


def _decorate_markup(kwargs: dict[str, Any]) -> None:
    markup = kwargs.get("reply_markup")
    rows = getattr(markup, "inline_keyboard", None) or getattr(markup, "keyboard", None)
    if not rows:
        return
    for row in rows:
        for button in row:
            text = getattr(button, "text", None)
            if not isinstance(text, str):
                continue
            source = next((item for item in sorted(CUSTOM_EMOJI_IDS, key=len, reverse=True) if item in text), None)
            if source is not None and hasattr(button, "icon_custom_emoji_id"):
                button.icon_custom_emoji_id = CUSTOM_EMOJI_IDS[source]
                # Both inline and reply buttons have a dedicated icon slot.
                # Remove textual fallbacks so exactly one premium emoji is
                # rendered. Incoming handlers accept the plain labels below.
                button.text = strip_custom_emoji_fallbacks(text)


def install() -> None:
    """Install one process-wide outgoing-message decorator for all bots."""
    if getattr(Bot, "_godofdars_custom_emoji_installed", False):
        return

    original_send_message = Bot.send_message
    original_edit_message_text = Bot.edit_message_text
    original_send_photo = Bot.send_photo
    original_edit_message_caption = Bot.edit_message_caption
    original_call = Bot.__call__

    @wraps(original_send_message)
    async def send_message(self: Bot, *args: Any, **kwargs: Any) -> Any:
        _add_group_reply(kwargs)
        _decorate(kwargs, "text", "entities")
        _decorate_markup(kwargs)
        return await original_send_message(self, *args, **kwargs)

    @wraps(original_edit_message_text)
    async def edit_message_text(self: Bot, *args: Any, **kwargs: Any) -> Any:
        _decorate(kwargs, "text", "entities")
        _decorate_markup(kwargs)
        return await original_edit_message_text(self, *args, **kwargs)

    @wraps(original_send_photo)
    async def send_photo(self: Bot, *args: Any, **kwargs: Any) -> Any:
        _add_group_reply(kwargs)
        _decorate(kwargs, "caption", "caption_entities")
        _decorate_markup(kwargs)
        return await original_send_photo(self, *args, **kwargs)

    @wraps(original_edit_message_caption)
    async def edit_message_caption(self: Bot, *args: Any, **kwargs: Any) -> Any:
        _decorate(kwargs, "caption", "caption_entities")
        _decorate_markup(kwargs)
        return await original_edit_message_caption(self, *args, **kwargs)

    @wraps(original_call)
    async def call(self: Bot, method: Any, *args: Any, **kwargs: Any) -> Any:
        _decorate_method(method)
        try:
            return await original_call(self, method, *args, **kwargs)
        except TelegramBadRequest as exc:
            # Callback queries expire quickly. A late acknowledgement must not
            # crash polling after the requested database operation completed.
            description = str(exc).lower()
            if (
                method.__class__.__name__ == "AnswerCallbackQuery"
                and ("query is too old" in description or "query id is invalid" in description)
            ):
                return None
            raise

    Bot.send_message = send_message  # type: ignore[method-assign]
    Bot.edit_message_text = edit_message_text  # type: ignore[method-assign]
    Bot.send_photo = send_photo  # type: ignore[method-assign]
    Bot.edit_message_caption = edit_message_caption  # type: ignore[method-assign]
    Bot.__call__ = call  # type: ignore[method-assign]
    Bot._godofdars_custom_emoji_installed = True
