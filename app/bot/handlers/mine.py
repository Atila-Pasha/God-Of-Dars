from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import MineCallback
from app.bot.keyboards.main_menu import MENU_SECTION_BY_LABEL, main_menu_keyboard
from app.bot.keyboards.mine import mine_keyboard, mine_upgrade_confirmation_keyboard
from app.bot.utils.telegram import safe_edit_text
from app.core.game_logic import GameConfigurationError
from app.services.mine_service import MineService
from app.services.school_errors import (
    InsufficientCoins,
    MineLevelLocked,
    MineNotFound,
    MineUpgradeUnavailable,
    ResourceNotFound,
)
from app.services.user_service import UserInactiveError, UserService

router = Router(name="mine")
mine_service = MineService()
user_service = UserService()
MINE_LABEL = next(
    label for label, section in MENU_SECTION_BY_LABEL.items() if section == "mine"
)


def _mine_text(snapshot) -> str:
    production = snapshot.production
    return (
        "⛏ معدن منابع\n\n"
        f"🏗 سطح معدن: {snapshot.level}\n"
        f"⚙️ تولید فعلی: هر دقیقه {production.coin_per_minute} طلا، "
        f"{production.diamond_per_minute} الماس\n"
        f"⏱️ زمان محاسبه‌شده: {snapshot.collected_minutes} دقیقه\n\n"
        "📦 دریافت امروز:\n"
        f"🪙 طلا: {snapshot.today_coin}\n"
        f"💎 الماس: {snapshot.today_diamond}"
    )


def _upgrade_text(snapshot, next_level) -> str:
    current = snapshot.production
    return (
        "⬆️ پیش‌نمایش ارتقای معدن\n\n"
        f"سطح فعلی: {snapshot.level}\n"
        f"سطح بعدی: {snapshot.level + 1}\n\n"
        "📈 تولید جدید در هر دقیقه:\n"
        f"🪙 طلا: {next_level.coin_per_minute} "
        f"(تغییر: {next_level.coin_per_minute - current.coin_per_minute:+d})\n"
        f"💎 الماس: {next_level.diamond_per_minute} "
        f"(تغییر: {next_level.diamond_per_minute - current.diamond_per_minute:+d})\n\n"
        f"💎 هزینه ارتقا: {next_level.diamond_cost} الماس\n\n"
        "آیا ارتقای معدن را تأیید می‌کنی؟"
    )


async def _show(target: Message | CallbackQuery, session: AsyncSession) -> None:
    user = await user_service.get_active_by_telegram_user_id(
        session, target.from_user.id
    )
    snapshot = await mine_service.open(session, user.id)
    can_upgrade = True
    try:
        mine_service.config.mine_upgrade(snapshot.level, user.level)
    except GameConfigurationError:
        can_upgrade = False
    text = _mine_text(snapshot)
    markup = mine_keyboard(can_upgrade=can_upgrade)
    if isinstance(target, CallbackQuery) and target.message is not None:
        await safe_edit_text(target.message, text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


async def mine_handler(message: Message, session: AsyncSession | None = None) -> None:
    # The dispatcher injects the database session when called as a handler.
    if session is None or message.from_user is None:
        return
    try:
        await _show(message, session)
    except (UserInactiveError, MineNotFound, ResourceNotFound):
        await message.answer(
            "اطلاعات معدن در دسترس نیست.", reply_markup=main_menu_keyboard()
        )


@router.message(F.text == MINE_LABEL)
async def mine_message(message: Message, session: AsyncSession) -> None:
    await mine_handler(message, session)


@router.callback_query(MineCallback.filter())
async def mine_callback(
    callback: CallbackQuery, callback_data: MineCallback, session: AsyncSession
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        user = await user_service.get_active_by_telegram_user_id(
            session, callback.from_user.id
        )
        if callback_data.action == "back":
            await callback.message.answer(
                "به منوی اصلی برگشتید.", reply_markup=main_menu_keyboard()
            )
        elif callback_data.action == "collect":
            snapshot, amounts = await mine_service.collect(session, user.id)
            labels = ("طلا", "الماس", "XP")
            collected = "، ".join(
                f"{amount} {label}"
                for label, amount in zip(labels, amounts, strict=True)
                if amount
            )
            await safe_edit_text(
                callback.message,
                _mine_text(snapshot),
                reply_markup=mine_keyboard(can_upgrade=True),
            )
            await callback.answer(
                f"منابع برداشت شد: {collected}"
                if collected
                else "منبع قابل برداشتی ندارید."
            )
            return
        elif callback_data.action == "upgrade":
            snapshot = await mine_service.open(session, user.id)
            try:
                next_level = mine_service.config.mine_upgrade(
                    snapshot.level, user.level
                )
            except GameConfigurationError as exc:
                if "locked" in str(exc).lower():
                    raise MineLevelLocked from exc
                raise MineUpgradeUnavailable from exc
            await safe_edit_text(
                callback.message,
                _upgrade_text(snapshot, next_level),
                reply_markup=mine_upgrade_confirmation_keyboard(),
            )
            await callback.answer()
            return
        elif callback_data.action == "cancel_upgrade":
            await _show(callback, session)
            await callback.answer("ارتقا لغو شد.")
            return
        else:  # confirm_upgrade
            snapshot = await mine_service.upgrade(session, user.id)
            can_upgrade = True
            try:
                mine_service.config.mine_upgrade(snapshot.level, user.level)
            except GameConfigurationError:
                can_upgrade = False
            await safe_edit_text(
                callback.message,
                _mine_text(snapshot),
                reply_markup=mine_keyboard(can_upgrade=can_upgrade),
            )
            await callback.answer("معدن با موفقیت ارتقا پیدا کرد.")
            return
        await callback.answer()
    except InsufficientCoins:
        await callback.answer("الماس کافی برای ارتقای معدن ندارید.", show_alert=True)
    except MineLevelLocked:
        await callback.answer(
            "سطح کاربر برای ارتقای بعدی معدن کافی نیست.", show_alert=True
        )
    except (MineNotFound, MineUpgradeUnavailable, ResourceNotFound, UserInactiveError):
        await callback.answer("این عملیات معدن در دسترس نیست.", show_alert=True)
