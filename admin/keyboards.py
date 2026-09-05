from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
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
        ("نام", "name"), ("درصد کاهش", "reduction_percent"),
        ("جذب ثابت", "flat_absorption"), ("قیمت خرید", "purchase_price"),
        ("سطح بازشدن", "unlock_level"), ("توضیح", "description"),
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
