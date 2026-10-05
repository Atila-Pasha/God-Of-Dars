from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.banners import (
    BANANA,
    COIN,
    DIAMOND,
    FORT,
    LOOT,
    MARKDOWN_V2,
    bold,
    emoji,
    escape,
    section_entry_banner,
)
from app.bot.callbacks import MineCallback
from app.bot.keyboards.main_menu import (
    MENU_SECTION_BY_LABEL,
    main_menu_keyboard,
    section_back_keyboard,
)
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
    daily_limit = mine_service.config.mine_max_catchup_minutes
    ready = snapshot.today_coin > 0 or snapshot.today_diamond > 0
    status = (
        f"{emoji('5823388325188214894', '✅')} محموله آمادهٔ برداشت است\\."
        if ready
        else f"{emoji('6039539366177541657', '⏳')} کوره‌ها مشغول کارند؛ کمی دیگر سر بزن\\."
    )
    coin_scale = max(1, production.coin_per_minute * daily_limit)
    diamond_scale = production.diamond_per_minute * daily_limit
    if diamond_scale:
        diamond_stock = (
            f"موجودی قابل برداشت: {bold(_ltr(f'{snapshot.today_diamond:,}'))} {DIAMOND}\n"
            f"{_ore_bar(snapshot.today_diamond, diamond_scale)}"
        )
    else:
        diamond_stock = (
            f"موجودی قابل برداشت: {bold(_ltr(f'{snapshot.today_diamond:,}'))} {DIAMOND}\n"
            f"{_ore_bar(0, 1)}\n"
            "تولید الماس در این سطح هنوز فعال نیست\\."
        )
    return (
        f"{emoji('5823474022670671455', '⛏️')} {bold('معدن فرماندهی')} {emoji('5935912783261470019', '✨')}\n\n"
        f"{FORT} سطح معدن: {bold(snapshot.level)}\n"
        f"{emoji('6039539366177541657', '⚙️')} زمان تولید محاسبه‌شده: {escape(snapshot.collected_minutes)} دقیقه\n\n"
        f"{emoji('6007857303695400402', '📈')} {bold('تولید در هر دقیقه')}:\n\n"
        f"{COIN} طلا: {escape(production.coin_per_minute)}\n"
        f"{DIAMOND} الماس: {escape(production.diamond_per_minute)}\n\n"
        f"{LOOT} {bold('محمولهٔ فعلی معدن')}:\n\n"
        f"{DIAMOND} {bold('معدن الماس')}\n"
        f"{diamond_stock}\n\n"
        f"{emoji('5823329527085931340', '🪙')} {bold('معدن طلا')}\n"
        f"موجودی قابل برداشت: {bold(_ltr(f'{snapshot.today_coin:,}'))} {emoji('5823329527085931340', '🪙')}\n"
        f"{_ore_bar(snapshot.today_coin, coin_scale)}\n\n"
        f"سقف تولید روزانه: {escape(daily_limit // 60)} ساعت؛ محمولهٔ برداشت‌نشده باقی می‌ماند\\.\n\n"
        f"{status}"
    )


def _ore_bar(amount: int, scale: int) -> str:
    """Render eight adjoining custom-emoji cells in physical left-to-right order."""
    scale = max(1, scale)
    fill = max(0.0, min(8.0, 8 * amount / scale))
    percent = min(100, max(0, amount * 100 // scale))
    empty = ("5931534188657254206", "5933785859621920322", "5931275038920548077")
    complete = ("5949744124142820550", "5949736114028814482", "5947346029153100052")
    partial = (
        ("5949346577674935537", "5949509477194537601", "5949308223616982431"),
        ("5947466314007192098", "5947256955826363081", "5949707002740481824"),
        ("5949257543002889576", "5949513969730330381", "5947323523524468309"),
    )
    cells = []
    for index in range(8):
        kind = 0 if index == 0 else 2 if index == 7 else 1
        portion = max(0.0, min(1.0, fill - (7 - index)))
        if portion <= 0:
            icon_id = empty[kind]
        elif portion >= 1:
            icon_id = complete[kind]
        else:
            icon_id = partial[kind][min(2, int(portion * 3))]
        cells.append(emoji(icon_id, "▫️"))
    return _ltr("".join(cells)) + "  " + _ltr(f"{percent}%")


def _ltr(value: str) -> str:
    """Keep amounts and progress bars in reading order inside Persian text."""
    return f"\u2066{value}\u2069"


def _upgrade_text(snapshot, next_level) -> str:
    current = snapshot.production
    banana_reward = mine_service.config.upgrade_banana_reward(
        next_level.diamond_cost or 0
    )
    return (
        f"{emoji('5866060208253441223', '⬆️')} {bold('ارتقای معدن | پیش‌نمایش')} {emoji('5282843764451195532', '✨')}\n\n"
        f"{bold('سطح:')} {escape(snapshot.level)} {emoji('5235470399730361615', '➡️')} {escape(snapshot.level + 1)}\n\n"
        f"{emoji('6007857303695400402', '📈')} {bold('تولید جدید در هر دقیقه:')}\n\n"
        f"{COIN} {bold('طلا:')} {bold(next_level.coin_per_minute)}  « تغییر: {escape(f'{next_level.coin_per_minute - current.coin_per_minute:+d}')} »\n"
        f"{DIAMOND} {bold('الماس:')} {bold(next_level.diamond_per_minute)}  « تغییر: {escape(f'{next_level.diamond_per_minute - current.diamond_per_minute:+d}')} »\n\n"
        f"{emoji('5823196980100211145', '💎')} {bold('هزینه ارتقا:')} {escape(next_level.diamond_cost)} الماس {DIAMOND}\n\n"
        f"{emoji('5825447362574688486', '🎁')} {bold('پاداش ارتقا:')} {escape(banana_reward)} {bold('موز')} {BANANA}\n\n"
        f"{emoji('5832384984593206481', '🔥')} آماده‌ای تولید معدن رو یک پله منفجر کنی؟"
    )


async def _show(target: Message | CallbackQuery, session: AsyncSession) -> None:
    if target.from_user is None:
        raise UserInactiveError
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
        await safe_edit_text(
            target.message, text, reply_markup=markup, parse_mode=MARKDOWN_V2
        )
    else:
        if isinstance(target, Message):
            await target.answer(
                section_entry_banner("معدن"),
                reply_markup=section_back_keyboard(),
                parse_mode=MARKDOWN_V2,
            )
        await target.answer(text, reply_markup=markup, parse_mode=MARKDOWN_V2)


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
            labels = ("طلا", "الماس", "موز")
            collected = "، ".join(
                f"{amount} {label}"
                for label, amount in zip(labels, amounts, strict=True)
                if amount
            )
            await safe_edit_text(
                callback.message,
                _mine_text(snapshot),
                reply_markup=mine_keyboard(can_upgrade=True),
                parse_mode=MARKDOWN_V2,
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
                parse_mode=MARKDOWN_V2,
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
                parse_mode=MARKDOWN_V2,
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
