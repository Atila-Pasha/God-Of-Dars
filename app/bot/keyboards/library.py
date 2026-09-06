from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import LibraryCallback, LibraryTeacherCallback, StudyCallback
from app.bot.custom_emojis import premium_emoji_id


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
                ),
                InlineKeyboardButton(
                    text="👨‍🏫 معرفی دبیرها",
                    callback_data=LibraryCallback(action="teachers").pack(),
                ),
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


def teacher_library_keyboard(
    teachers: list[object], *, page: int, page_count: int
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"👨‍🏫 {teacher.name}",
                icon_custom_emoji_id=premium_emoji_id(
                    teacher.emoji, fallback="👨‍🏫"
                ),
                callback_data=LibraryTeacherCallback(
                    action="view", teacher_id=teacher.id, page=page
                ).pack(),
            )
        ]
        for teacher in teachers
    ]
    navigation = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="◀️ قبلی",
                callback_data=LibraryTeacherCallback(
                    action="page", page=page - 1
                ).pack(),
            )
        )
    if page < page_count - 1:
        navigation.append(
            InlineKeyboardButton(
                text="بعدی ▶️",
                callback_data=LibraryTeacherCallback(
                    action="page", page=page + 1
                ).pack(),
            )
        )
    if navigation:
        rows.append(navigation)
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 کتابخانه",
                callback_data=LibraryTeacherCallback(action="back").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def teacher_library_detail_keyboard(page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 فهرست دبیرها",
                    callback_data=LibraryTeacherCallback(
                        action="page", page=page
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📚 کتابخانه",
                    callback_data=LibraryTeacherCallback(action="back").pack(),
                )
            ],
        ]
    )
