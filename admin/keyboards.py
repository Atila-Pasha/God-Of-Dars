from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def daily_quest_dates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="امروز", callback_data="admin_daily:date:today"),
                InlineKeyboardButton(
                    text="فردا", callback_data="admin_daily:date:tomorrow"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="تاریخ دیگر", callback_data="admin_daily:date:custom"
                )
            ],
        ]
    )


def daily_quest_types(types: tuple[str, ...]) -> InlineKeyboardMarkup:
    labels = {
        "DAILY_LOGIN": "🔐 ورود روزانه",
        "ANSWER_DAILY_QUESTION": "❓ پاسخ به سؤال روزانه",
        "CORRECT_ANSWERS": "🧠 پاسخ صحیح به سؤال‌ها",
        "COMPLETE_BATTLES": "⚔️ انجام نبردها",
        "WIN_BATTLES": "🏆 بردن نبردها",
        "COLLECT_MINE": "⛏ جمع‌آوری معدن",
        "JOIN_CHANNEL": "📢 عضویت در کانال",
    }
    rows = [
        [
            InlineKeyboardButton(
                text=labels.get(item, item),
                callback_data=f"admin_daily:type:{item}",
            )
        ]
        for item in types
    ]
    rows.append(
        [InlineKeyboardButton(text="❌ لغو", callback_data="admin_daily:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def daily_quest_rewards() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🪙 سکه", callback_data="admin_daily:reward:COIN"),
                InlineKeyboardButton(
                    text="💎 الماس", callback_data="admin_daily:reward:DIAMOND"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🍌 موز", callback_data="admin_daily:reward:BANANA"
                ),
                InlineKeyboardButton(
                    text="✅ پایان پاداش‌ها", callback_data="admin_daily:reward:done"
                ),
            ],
        ]
    )


def main() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="👤 مدیریت کاربران"),
                KeyboardButton(text="👨‍🏫 مدیریت دبیرها"),
            ],
            [KeyboardButton(text="🛡 مدیریت سپرها")],
            [KeyboardButton(text="📢 مدیریت قفل کانال")],
            [KeyboardButton(text="🎁 ارسال جعبه شانس"), KeyboardButton(text="🃏 ارسال کارت شانس")],
            [
                KeyboardButton(text="❓ ساخت سؤال روزانه"),
                KeyboardButton(text="👥 ساخت سؤال گروهی"),
            ],
            [KeyboardButton(text="🎯 مدیریت فعالیت‌های روزانه")],
            [KeyboardButton(text="📖 مدیریت پک‌های مطالعه")],
            [KeyboardButton(text="📣 پیام همگانی")],
            [KeyboardButton(text="❌ لغو")],
        ],
        resize_keyboard=True,
    )


def chance_box_sections() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 ارسال به بخش ۱"), KeyboardButton(text="📦 ارسال به بخش ۲")],
            [KeyboardButton(text="📦 ارسال به بخش ۳"), KeyboardButton(text="📦 ارسال به بخش ۴")],
            [KeyboardButton(text="❌ لغو")],
        ],
        resize_keyboard=True,
    )


def user_actions(user_id: int, active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ فعال‌سازی" if not active else "⛔ مسدود کردن",
                    callback_data=f"user:toggle:{user_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 تغییر منابع", callback_data=f"user:resources:{user_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👨‍🏫 دبیرهای کاربر", callback_data=f"user:teachers:{user_id}"
                )
            ],
        ]
    )


def user_teacher_actions(user_id: int, user_teacher_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 حذف دبیر",
                    callback_data=f"user_teacher:delete:{user_id}:{user_teacher_id}",
                )
            ],
        ]
    )


def user_teacher_list(user_id: int, teachers) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"🗑 حذف {item.teacher.name}",
                callback_data=f"user_teacher:delete:{user_id}:{item.id}",
            )
        ]
        for item in teachers
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 بستن", callback_data=f"user_teacher:close:{user_id}"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def teacher_actions(teacher_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ ویرایش", callback_data=f"teacher:edit:{teacher_id}"
                ),
                InlineKeyboardButton(
                    text="🗑 حذف", callback_data=f"teacher:delete:{teacher_id}"
                ),
            ],
        ]
    )


def teacher_edit_fields(teacher_id: int) -> InlineKeyboardMarkup:
    fields = (
        ("نام", "name"), ("آسیب", "damage"), ("جان", "max_hp"),
        ("قیمت خرید", "purchase_price"), ("قیمت ارتقا", "upgrade_price"),
        ("سطح بازشدن", "unlock_level"), ("توانایی", "ability_text"),
        ("توضیحات", "description"),
        ("استیکر", "sticker"), ("اموجی", "emoji"),
    )
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"teacher:field:{teacher_id}:{field}")]
        for label, field in fields
    ]
    rows.append([InlineKeyboardButton(text="✅ پایان", callback_data=f"teacher:done:{teacher_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def shield_actions(shield_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ ویرایش", callback_data=f"shield:edit:{shield_id}"
                ),
                InlineKeyboardButton(
                    text="🗑 حذف", callback_data=f"shield:delete:{shield_id}"
                ),
            ],
        ]
    )


def shield_edit_fields(shield_id: int) -> InlineKeyboardMarkup:
    fields = (
        ("نام", "name"), ("قیمت خرید", "purchase_price"),
        ("ارز خرید", "purchase_resource"),
        ("سطح بازشدن", "unlock_level"), ("مدت (دقیقه)", "duration_minutes"),
        ("توضیح", "description"),
    )
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"shield:field:{shield_id}:{field}")]
        for label, field in fields
    ]
    rows.append([InlineKeyboardButton(text="✅ پایان", callback_data=f"shield:done:{shield_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ لغو")]], resize_keyboard=True
    )


def study_pack_actions(pack_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ ویرایش", callback_data=f"study_pack:edit:{pack_id}"
                ),
                InlineKeyboardButton(
                    text="🗑 حذف", callback_data=f"study_pack:delete:{pack_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 فعال/غیرفعال",
                    callback_data=f"study_pack:toggle:{pack_id}",
                )
            ],
        ]
    )


def study_pack_edit_fields(pack_id: int) -> InlineKeyboardMarkup:
    fields = (
        ("کلید", "key"),
        ("نام نمایشی", "name"),
        ("مدت (دقیقه)", "duration_minutes"),
        ("نوع پاداش", "reward_resource"),
        ("مقدار پاداش", "reward_amount"),
    )
    rows = [
        [
            InlineKeyboardButton(
                text=label, callback_data=f"study_pack:field:{pack_id}:{field}"
            )
        ]
        for label, field in fields
    ]
    rows.append(
        [InlineKeyboardButton(text="✅ پایان", callback_data=f"study_pack:done:{pack_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
