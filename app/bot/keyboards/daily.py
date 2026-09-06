from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def daily_keyboard(progresses) -> InlineKeyboardMarkup:
    rows = []
    for item in progresses:
        quest = item.quest
        label = f"{'✅' if item.claimed else '🎁' if item.progress >= quest.target else '▫️'} {quest.title} ({item.progress}/{quest.target})"
        if not item.claimed and quest.quest_type == "JOIN_CHANNEL" and item.progress < quest.target:
            rows.append([InlineKeyboardButton(text=f"🔎 بررسی عضویت {label}", callback_data=f"daily:join:{item.id}")])
        elif not item.claimed and item.progress >= quest.target:
            rows.append(
                [InlineKeyboardButton(text=label, callback_data=f"daily:claim:{item.id}")]
            )
        else:
            rows.append([InlineKeyboardButton(text=label, callback_data="daily:noop")])
    return InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="بازگشت", callback_data="daily:noop")]])
