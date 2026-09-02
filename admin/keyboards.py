from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👤 مدیریت کاربران"), KeyboardButton(text="👨‍🏫 مدیریت دبیرها")],
        [KeyboardButton(text="❓ ساخت سؤال روزانه"), KeyboardButton(text="👥 ساخت سؤال گروهی")],
        [KeyboardButton(text="📣 پیام همگانی")],
        [KeyboardButton(text="❌ لغو")],
    ], resize_keyboard=True)


def user_actions(user_id: int, active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ فعال‌سازی" if not active else "⛔ مسدود کردن", callback_data=f"user:toggle:{user_id}")],
        [InlineKeyboardButton(text="💰 تغییر منابع", callback_data=f"user:resources:{user_id}")],
    ])


def teacher_actions(teacher_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ ویرایش", callback_data=f"teacher:edit:{teacher_id}"), InlineKeyboardButton(text="🗑 حذف", callback_data=f"teacher:delete:{teacher_id}")],
    ])
