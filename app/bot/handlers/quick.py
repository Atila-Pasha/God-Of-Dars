from random import choice

from aiogram import F, Router
from aiogram.types import Message

router = Router(name="quick_replies")

GOD_REPLIES = (
    "سلام فرمانده! آماده‌ای امروز یه قدم جلوتر بری؟ 👋",
    "چخبر فرمانده؟ درس خوندی یا نه؟ 📚",
    "گاد اینجاست؛ بگو امروز چه نقشه‌ای داری! ⚔️",
    "یه سؤال حل کن، یه قدم به پیروزی نزدیک‌تر شو! ✨",
    "فرمانده، دبیرهات منتظر دستور تو هستن! 👨‍🏫",
    "سلام! امروز رکورد خودت رو جابه‌جا می‌کنی؟ 🏆",
)


@router.message(F.text == "گاد")
async def god_reply_handler(message: Message) -> None:
    await message.answer(choice(GOD_REPLIES))
