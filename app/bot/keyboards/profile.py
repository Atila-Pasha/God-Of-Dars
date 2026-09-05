from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import LevelConfirmationCallback, ProfileCallback


def profile_keyboard(
    *, include_delete: bool = False, owner_id: int = 0
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="👤 اطلاعات پروفایل",
                callback_data=ProfileCallback(
                    action="profile", owner_id=owner_id
                ).pack(),
            ),
            InlineKeyboardButton(
                text="⚔️ اطلاعات جنگ",
                callback_data=ProfileCallback(action="war", owner_id=owner_id).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text="🏰 دارایی و قلمرو",
                callback_data=ProfileCallback(
                    action="assets", owner_id=owner_id
                ).pack(),
            ),
            InlineKeyboardButton(
                text="📚 دانش و دعوت‌ها",
                callback_data=ProfileCallback(
                    action="knowledge", owner_id=owner_id
                ).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text="⬆️ ارتقای سطح",
                callback_data=ProfileCallback(
                    action="upgrade", owner_id=owner_id
                ).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 بازگشت به منوی اصلی",
                callback_data=ProfileCallback(action="back", owner_id=owner_id).pack(),
            )
        ],
    ]
    if include_delete:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 حذف پیام اطلاعات",
                    callback_data=ProfileCallback(
                        action="delete", owner_id=owner_id
                    ).pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def level_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تأیید ارتقا",
                    callback_data=LevelConfirmationCallback(decision="confirm").pack(),
                ),
                InlineKeyboardButton(
                    text="❌ لغو",
                    callback_data=LevelConfirmationCallback(decision="cancel").pack(),
                ),
            ]
        ]
    )
