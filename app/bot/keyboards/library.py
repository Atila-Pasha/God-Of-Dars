from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import (
    LibraryCallback,
    LibraryShieldCallback,
    LibraryTeacherCallback,
    StudyCallback,
)
from app.bot.custom_emojis import premium_emoji_id
from app.bot.keyboards.buffet import SHIELD_ICONS
from app.models.shield import Shield
from app.models.study_pack import StudyPack
from app.models.teacher import Teacher


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
                    text="ثبت ساعت مطالعه",
                    icon_custom_emoji_id="5825736654391876714",
                    callback_data=LibraryCallback(action="study").pack(),
                ),
                InlineKeyboardButton(
                    text="👨‍🏫 معرفی دبیرها",
                    callback_data=LibraryCallback(action="teachers").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="معرفی سپرها",
                    icon_custom_emoji_id="5825861861278490879",
                    callback_data=LibraryCallback(action="shields").pack(),
                )
            ],
        ]
    )


def shield_library_keyboard(shields: Sequence[Shield]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=shield.name,
                icon_custom_emoji_id=SHIELD_ICONS.get(
                    shield.name, "5825861861278490879"
                ),
                callback_data=LibraryShieldCallback(
                    action="view", shield_id=shield.id
                ).pack(),
            )
        ]
        for shield in shields
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="بازگشت به کتابخانه",
                icon_custom_emoji_id="5235864325540815679",
                callback_data=LibraryCallback(action="back").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def shield_library_detail_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="بازگشت به فهرست سپرها",
                    icon_custom_emoji_id="5235864325540815679",
                    callback_data=LibraryShieldCallback(action="back").pack(),
                )
            ]
        ]
    )


def study_keyboard(packs: Sequence[StudyPack]) -> InlineKeyboardMarkup:
    rows = []
    for pack in packs:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"⏱ {pack.name} ({pack.duration_minutes} دقیقه) — "
                    f"{pack.reward_amount} {('طلا' if pack.reward_resource == 'COIN' else 'الماس')}",
                    callback_data=StudyCallback(pack_key=pack.key).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 کتابخانه", callback_data=LibraryCallback(action="back").pack()
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def answer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ پاسخ دادن",
                    callback_data=LibraryCallback(action="answer").pack(),
                ),
                InlineKeyboardButton(
                    text="❌ لغو",
                    callback_data=LibraryCallback(action="cancel").pack(),
                ),
            ]
        ]
    )


def teacher_library_keyboard(
    teachers: Sequence[Teacher], *, page: int, page_count: int
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"👨‍🏫 {teacher.name}",
                icon_custom_emoji_id=premium_emoji_id(teacher.emoji, fallback="👨‍🏫"),
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
                text="قبلی",
                icon_custom_emoji_id="5235470399730361615",
                callback_data=LibraryTeacherCallback(
                    action="page", page=page - 1
                ).pack(),
            )
        )
    if page < page_count - 1:
        navigation.append(
            InlineKeyboardButton(
                text="بعدی",
                icon_custom_emoji_id="5233475649414373111",
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
