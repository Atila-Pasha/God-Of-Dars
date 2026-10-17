"""Buffet purchases and school management for archers and arrow packs."""

from typing import Any

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import archer_banners as ab
from app.bot import knight_banners as kb
from app.bot.banners import MARKDOWN_V2
from app.bot.callbacks import ArcherAction, ArcherCallback, SchoolCallback
from app.bot.keyboards.main_menu import main_menu_keyboard
from app.bot.utils.telegram import safe_edit_text
from app.core.enums import ResourceType
from app.services.archer_service import ArcherError, ArcherService
from app.services.knight_service import KnightService
from app.services.school_errors import (
    InsufficientCoins,
    InsufficientDiamonds,
    SchoolUserNotFound,
)
from app.services.user_service import UserInactiveError, UserService

router = Router(name="archers")
service = ArcherService()
knights = KnightService()
users = UserService()
ARCHER_ICON = "5402133431670816471"
ARROW_ICON = "5314526780416092636"
UPGRADE_ICON = "5823677853228605366"
SELL_ICON = "5825656871079387950"
BACK_ICON = "5235864325540815679"


def school_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="بازگشت",
                    icon_custom_emoji_id=BACK_ICON,
                    callback_data=SchoolCallback(action="archers").pack(),
                )
            ]
        ]
    )


def knight_back() -> InlineKeyboardMarkup:
    return keyboard(
        [
            [
                InlineKeyboardButton(
                    text="بازگشت",
                    icon_custom_emoji_id=BACK_ICON,
                    callback_data=SchoolCallback(action="knights").pack(),
                )
            ]
        ]
    )


async def banner(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup,
    edit: bool = True,
) -> None:
    content = text
    if edit:
        await safe_edit_text(
            message, content, reply_markup=reply_markup, parse_mode=MARKDOWN_V2
        )
    else:
        await message.answer(content, reply_markup=reply_markup, parse_mode=MARKDOWN_V2)


def button(
    title: str, action: ArcherAction, item_id: int = 0, icon: str | None = None
) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=title,
        icon_custom_emoji_id=icon,
        callback_data=ArcherCallback(action=action, item_id=item_id).pack(),
    )


def keyboard(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back(action: ArcherAction, item_id: int = 0) -> InlineKeyboardButton:
    return button("بازگشت", action, item_id, BACK_ICON)


async def show_menu(
    message: Message, session: AsyncSession, user_id: int, *, edit: bool = False
) -> None:
    await banner(
        message,
        ab.buffet_entry(),
        reply_markup=keyboard(
            [
                [button("کماندارها", "archers", icon=ARCHER_ICON)],
                [button("تیر کماندار", "packs", icon=ARROW_ICON)],
                [button("شوالیه", "knights", icon=kb.KNIGHT)],
                [back("back_buffet")],
            ]
        ),
        edit=edit,
    )


@router.message(
    F.chat.type == "private",
    F.text.in_({"دفاع دژ", "کماندار ها", "کماندارها", "شوالیه ها", "شوالیه‌ها"}),
)
async def menu(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    try:
        user = await users.get_active_by_telegram_user_id(session, message.from_user.id)
        await show_menu(message, session, user.id)
    except (SchoolUserNotFound, UserInactiveError):
        await message.answer("حساب شما فعال نیست.", reply_markup=main_menu_keyboard())


@router.callback_query(ArcherCallback.filter())
async def callback(
    callback: CallbackQuery, callback_data: ArcherCallback, session: AsyncSession
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    try:
        user = await users.get_active_by_telegram_user_id(
            session, callback.from_user.id
        )
        action = callback_data.action
        catalog: list[Any]
        item: Any
        if action in {"knight_heal", "confirm_knight_heal"}:
            raise ArcherError("شوالیه درمان نمی‌شود. با صفرشدن جان، از مدرسه حذف می‌شود.")
        if action == "menu":
            await show_menu(callback.message, session, user.id, edit=True)
        elif action == "back_buffet":
            from app.bot.handlers.buffet import _buffet_menu_banner

            await safe_edit_text(
                callback.message,
                _buffet_menu_banner(),
                reply_markup=None,
                parse_mode=MARKDOWN_V2,
            )
        elif action == "archers":
            catalog = await service.catalog(session)
            rows = [
                [
                    button(
                        f"{item.name} — قدرت {item.power}، سطح {item.unlock_level}، {item.purchase_price} {'الماس' if item.purchase_resource is ResourceType.DIAMOND else 'طلا'}",
                        "buy_archer",
                        item.id,
                        ARCHER_ICON,
                    )
                ]
                for item in catalog
            ]
            rows.append([back("menu")])
            await banner(
                callback.message,
                ab.archer_catalog(),
                reply_markup=keyboard(rows),
            )
        elif action == "knights":
            catalog = await knights.catalog(session)
            rows = [
                [
                    button(
                        f"{item.name} — قدرت {item.power}، جان {item.max_hp}، سطح {item.unlock_level}، {item.purchase_price} {'الماس' if item.purchase_resource is ResourceType.DIAMOND else 'طلا'}",
                        "buy_knight",
                        item.id,
                        kb.KNIGHT,
                    )
                ]
                for item in catalog
            ]
            rows.append([back("menu")])
            await banner(callback.message, kb.catalog(), reply_markup=keyboard(rows))
        elif action == "buy_knight":
            item = next(
                (
                    row
                    for row in await knights.catalog(session)
                    if row.id == callback_data.item_id
                ),
                None,
            )
            if item is None:
                raise ArcherError("شوالیه در دسترس نیست.")
            await banner(
                callback.message,
                kb.purchase(item),
                reply_markup=keyboard(
                    [
                        [
                            button("✅ تأیید خرید", "confirm_knight", item.id),
                            back("knights"),
                        ]
                    ]
                ),
            )
        elif action == "confirm_knight":
            item = await knights.buy(session, user.id, callback_data.item_id)
            await session.commit()
            await banner(
                callback.message,
                kb.bought(item),
                reply_markup=keyboard([[back("knights")]]),
            )
        elif action in {"equip_knight", "equip_archer"}:
            kind = "knight" if action == "equip_knight" else "archer"
            await knights.equip(session, user.id, kind)
            equipped_knight = (
                await knights.owned(session, user.id) if kind == "knight" else None
            )
            await session.commit()
            await banner(
                callback.message,
                f"{kb.name(equipped_knight.knight.name, equipped_knight.knight.emoji) if equipped_knight else ab.archer_name('کماندار')} {ab.escape('فعال شد.')}",
                reply_markup=knight_back() if kind == "knight" else school_back(),
            )
        elif action in {"knight_upgrade", "knight_sell"}:
            item = await knights.owned(session, user.id)
            if item is None or item.id != callback_data.item_id:
                raise ArcherError("شوالیه پیدا نشد.")
            confirm: ArcherAction
            if action == "knight_upgrade":
                text, confirm = kb.upgrade_preview(item), "confirm_knight_upgrade"
            elif action == "knight_sell":
                text, confirm = kb.sell_preview(item), "confirm_knight_sell"
            await banner(
                callback.message,
                text,
                reply_markup=keyboard(
                    [
                        [
                            button("✅ تأیید", confirm, item.id),
                            knight_back().inline_keyboard[0][0],
                        ]
                    ]
                ),
            )
        elif action == "confirm_knight_upgrade":
            item = await knights.upgrade(session, user.id, callback_data.item_id)
            await session.commit()
            await banner(
                callback.message,
                f"{kb.name(item.knight.name, item.knight.emoji)} {ab.escape('ارتقا یافت.')}\n{ab.escape(f'سطح {item.level}، جان {item.current_hp} HP')}",
                reply_markup=knight_back(),
            )
        elif action == "confirm_knight_sell":
            name, refund, currency = await knights.sell(
                session, user.id, callback_data.item_id
            )
            await session.commit()
            await banner(
                callback.message,
                f"{kb.name(name)} {ab.escape('فروخته شد.')}\n{kb.quote(kb.plain_price(refund, currency) + ' ' + ab.escape('بازگشت.'))}",
                reply_markup=knight_back(),
            )
        elif action == "packs":
            catalog = await service.packs(session)
            rows = [
                [
                    button(
                        f"{item.name} — {item.quantity} تیر، قدرت {item.power}، سطح {item.unlock_level}، {item.purchase_price} {'الماس' if item.purchase_resource is ResourceType.DIAMOND else 'طلا'}",
                        "buy_pack",
                        item.id,
                        ARROW_ICON,
                    )
                ]
                for item in catalog
            ]
            rows.append([back("menu")])
            await banner(
                callback.message,
                ab.pack_catalog(),
                reply_markup=keyboard(rows),
            )
        elif action == "owned":
            owned = await service.owned(session, user.id)
            rows = [
                [
                    button(
                        f"ارتقای {item.archer.name} | سطح {item.level} → {item.level + 1} | {service.upgrade_cost(item)} الماس",
                        "upgrade",
                        item.id,
                        ARCHER_ICON,
                    )
                ]
                for item in owned
            ]
            rows += [
                [
                    button(
                        f"فروش {item.archer.name} | بازگشت {item.archer.purchase_price // 2} {'الماس' if item.archer.purchase_resource is ResourceType.DIAMOND else 'طلا'}",
                        "sell",
                        item.id,
                        ARCHER_ICON,
                    )
                ]
                for item in owned
            ]
            rows.append(school_back().inline_keyboard[0])
            await banner(
                callback.message,
                ab.owned_catalog(owned),
                reply_markup=keyboard(rows),
            )
        elif action == "equip":
            if callback_data.item_id == 0:
                stocks = await service.ammunition(session, user.id)
                rows = [
                    [
                        button(
                            f"{item.pack.name} — {item.quantity} تیر{' ✅' if item.is_equipped else ''}",
                            "equip",
                            item.pack_id,
                            ARROW_ICON,
                        )
                    ]
                    for item in stocks
                ]
                rows.append(school_back().inline_keyboard[0])
                await banner(
                    callback.message,
                    ab.ammo_selection(),
                    reply_markup=keyboard(rows),
                )
            else:
                item = await service.equip_pack(session, user.id, callback_data.item_id)
                await session.commit()
                await banner(
                    callback.message,
                    ab.ammo_equipped(item.pack.name),
                    reply_markup=keyboard([[back("equip")]]),
                )
        elif action == "buy_archer":
            item = next(
                (
                    row
                    for row in await service.catalog(session)
                    if row.id == callback_data.item_id
                ),
                None,
            )
            if item is None:
                raise ArcherError("کماندار در دسترس نیست.")
            await banner(
                callback.message,
                ab.archer_purchase(item),
                reply_markup=keyboard(
                    [
                        [
                            button("✅ تأیید خرید", "confirm_archer", item.id),
                            back("archers"),
                        ]
                    ]
                ),
            )
        elif action == "buy_pack":
            item = next(
                (
                    row
                    for row in await service.packs(session)
                    if row.id == callback_data.item_id
                ),
                None,
            )
            if item is None:
                raise ArcherError("پک تیر در دسترس نیست.")
            await banner(
                callback.message,
                ab.pack_purchase(item),
                reply_markup=keyboard(
                    [
                        [
                            button("✅ تأیید خرید", "confirm_pack", item.id),
                            back("packs"),
                        ]
                    ]
                ),
            )
        elif action == "confirm_archer":
            item = await service.buy_archer(session, user.id, callback_data.item_id)
            await session.commit()
            await banner(
                callback.message,
                ab.archer_bought(item, service.power(item)),
                reply_markup=keyboard([[back("archers")]]),
            )
        elif action == "confirm_pack":
            item = await service.buy_pack(session, user.id, callback_data.item_id)
            await session.commit()
            await banner(
                callback.message,
                ab.pack_bought(item),
                reply_markup=keyboard([[back("packs")]]),
            )
        elif action == "upgrade":
            item = next(
                (
                    row
                    for row in await service.owned(session, user.id)
                    if row.id == callback_data.item_id
                ),
                None,
            )
            if item is None:
                raise ArcherError("کماندار پیدا نشد.")
            await banner(
                callback.message,
                ab.upgrade_preview(item, service.upgrade_cost(item)),
                reply_markup=keyboard(
                    [
                        [
                            button(
                                "تأیید ارتقا", "confirm_upgrade", item.id, UPGRADE_ICON
                            ),
                            school_back().inline_keyboard[0][0],
                        ]
                    ]
                ),
            )
        elif action == "confirm_upgrade":
            item = await service.upgrade(session, user.id, callback_data.item_id)
            await session.commit()
            await banner(
                callback.message,
                ab.upgrade_done(item, service.power(item)),
                reply_markup=school_back(),
            )
        elif action == "sell":
            item = next(
                (
                    row
                    for row in await service.owned(session, user.id)
                    if row.id == callback_data.item_id
                ),
                None,
            )
            if item is None:
                raise ArcherError("کماندار پیدا نشد.")
            await banner(
                callback.message,
                ab.sell_preview(item),
                reply_markup=keyboard(
                    [
                        [
                            button("تأیید فروش", "confirm_sell", item.id, SELL_ICON),
                            school_back().inline_keyboard[0][0],
                        ]
                    ]
                ),
            )
        elif action == "confirm_sell":
            name, refund, currency = await service.sell(
                session, user.id, callback_data.item_id
            )
            await session.commit()
            await banner(
                callback.message,
                ab.sell_done(name, refund, currency),
                reply_markup=school_back(),
            )
        await callback.answer()
    except (ArcherError, InsufficientCoins, InsufficientDiamonds) as exc:
        await session.rollback()
        reason = (
            "طلا کافی ندارید."
            if isinstance(exc, InsufficientCoins)
            else "الماس کافی ندارید."
            if isinstance(exc, InsufficientDiamonds)
            else str(exc)
        )
        await callback.answer(reason, show_alert=True)
    except (SchoolUserNotFound, UserInactiveError):
        await callback.answer("حساب شما فعال نیست.", show_alert=True)
