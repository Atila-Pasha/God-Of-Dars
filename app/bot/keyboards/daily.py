from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

QUEST_CHECK_LABELS = {
    "DAILY_LOGIN": "بررسی ورود روزانه",
    "ANSWER_DAILY_QUESTION": "بررسی پاسخ به سؤال روزانه",
    "CORRECT_ANSWERS": "بررسی پاسخ‌های صحیح",
    "COMPLETE_BATTLES": "بررسی انجام نبردها",
    "COLLECT_MINE": "بررسی جمع‌آوری معدن",
    "JOIN_CHANNEL": "بررسی عضویت در کانال",
}


def daily_keyboard(progresses) -> InlineKeyboardMarkup:
    rows = []
    for item in progresses:
        quest = item.quest
        if item.claimed:
            continue
        if quest.quest_type == "JOIN_CHANNEL" and item.progress < quest.target:
            invite_link = (quest.quest_metadata or {}).get("invite_link")
            if invite_link:
                rows.append(
                    [
                        InlineKeyboardButton(
                            text="🔗 ورود به کانال/گروه",
                            url=invite_link,
                        )
                    ]
                )
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"✅ {QUEST_CHECK_LABELS[quest.quest_type]}",
                        style="success",
                        callback_data=f"daily:join:{quest.id}:{item.id}",
                    )
                ]
            )
        elif item.progress >= quest.target:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="🎁 دریافت جایزه",
                        style="success",
                        callback_data=f"daily:claim:{item.id}",
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🔎 {QUEST_CHECK_LABELS.get(quest.quest_type, 'بررسی فعالیت')}",
                        callback_data=f"daily:claim:{item.id}",
                    )
                ]
            )
    return InlineKeyboardMarkup(
        inline_keyboard=rows
        or [[InlineKeyboardButton(text="بازگشت", callback_data="daily:noop")]]
    )
