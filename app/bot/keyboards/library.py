from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import LibraryCallback, StudyCallback


def library_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 سؤال روزانه",
                    callback_data=LibraryCallback(action="daily").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📖 ثبت مطالعه",
                    callback_data=LibraryCallback(action="study").pack(),
                )
            ],
        ]
    )


def study_keyboard(packs: dict[str, object]) -> InlineKeyboardMarkup:
    labels = {
        "half_hour": "⏱ پک نیم‌ساعته",
        "one_hour": "⏱ پک یک‌ساعته",
        "one_half_hour": "⏱ پک یک‌ونیم‌ساعته",
        "two_hours": "⏱ پک دوساعته",
    }
    rows = []
    for key, pack in packs.items():
        rows.append([InlineKeyboardButton(
            text=f"{labels.get(key, key)} — {pack.reward_amount} {('طلا' if pack.reward_resource.value == 'COIN' else 'الماس')}",
            callback_data=StudyCallback(pack_key=key).pack(),
        )])
    rows.append([InlineKeyboardButton(text="🔙 کتابخانه", callback_data=LibraryCallback(action="back").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def answer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ پاسخ دادن",
                    callback_data=LibraryCallback(action="daily").pack(),
                ),
                InlineKeyboardButton(
                    text="❌ لغو",
                    callback_data=LibraryCallback(action="cancel").pack(),
                ),
            ]
        ]
    )
