from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="battle")


@router.message(Command("attack"))
async def attack_command(message: Message) -> None:
    """Attack is intentionally command-only until the battle rules are enabled."""
    await message.answer("⚔️ سیستم حمله هنوز فعال نشده است؛ این فرمان بعداً تکمیل می‌شود.")
