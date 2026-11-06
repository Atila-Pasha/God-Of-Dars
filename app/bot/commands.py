"""Telegram command menus for the main bot's private and group chats."""

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

PRIVATE_COMMANDS = (
    BotCommand(command="start", description="شروع بازی و منوی اصلی"),
    BotCommand(command="global", description="جدول سراسری رنک"),
    BotCommand(command="rank", description="رنک، جام و پاداش‌های من"),
    BotCommand(command="game", description="فهرست بازی‌ها و شروع بازی"),
    BotCommand(command="attack", description="راهنمای حمله و نبرد"),
    BotCommand(command="leaderboard", description="برترین فرمانده‌ها و دانش‌آموزها"),
    BotCommand(command="profile", description="منوی پروفایل"),
    BotCommand(command="stat", description="اطلاعات پروفایل من"),
    BotCommand(command="war", description="کارنامهٔ جنگ من"),
    BotCommand(command="assets", description="دارایی‌های من"),
    BotCommand(command="knowledge", description="آمار دانش من"),
    BotCommand(command="referral", description="لینک دعوت دوستان"),
    BotCommand(command="help", description="راهنمای بازی"),
)

GROUP_COMMANDS = (
    BotCommand(command="global", description="جدول سراسری رنک"),
    BotCommand(command="rank", description="رنک و جام من"),
    BotCommand(command="attack", description="راهنمای حمله در گروه"),
    BotCommand(command="stat", description="اطلاعات پروفایل من"),
    BotCommand(command="war", description="کارنامهٔ جنگ من"),
    BotCommand(command="assets", description="دارایی‌های من"),
    BotCommand(command="knowledge", description="آمار دانش من"),
    BotCommand(command="help", description="راهنمای بازی"),
)


async def register_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        commands=list(PRIVATE_COMMANDS), scope=BotCommandScopeAllPrivateChats()
    )
    await bot.set_my_commands(
        commands=list(GROUP_COMMANDS), scope=BotCommandScopeAllGroupChats()
    )
