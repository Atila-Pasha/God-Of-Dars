"""Private buffet shop for archers and consumable arrow packs."""

from math import ceil

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import ArcherCallback
from app.bot.keyboards.main_menu import main_menu_keyboard
from app.core.enums import ResourceType
from app.services.archer_service import ArcherError, ArcherService
from app.services.school_errors import (
    InsufficientCoins,
    InsufficientDiamonds,
    SchoolUserNotFound,
)
from app.services.user_service import UserInactiveError, UserService

router = Router(name="archers")
service = ArcherService()
users = UserService()
ARCHER_ICON = "5402133431670816471"
ARROW_ICON = "5314526780416092636"


def button(
    title: str, action: str, item_id: int = 0, icon: str | None = None
) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=title,
        icon_custom_emoji_id=icon,
        callback_data=ArcherCallback(action=action, item_id=item_id).pack(),
    )


def keyboard(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_menu(message: Message, session: AsyncSession, user_id: int) -> None:
    archers = await service.owned(session, user_id)
    arrows = await service.ammunition(session, user_id)
    lines = [
        "🏹 کماندارهای دژ",
        "",
        "کماندارها هنگام حمله به دژ، با تیرهای موجود به دبیرها آسیب می‌زنند.",
        "فقط یک کماندار می‌توانید داشته باشید؛ برای تعویض باید کماندار فعلی را بفروشید.",
    ]
    lines += [
        f"{item.archer.name} — سطح {item.level}، قدرت {service.power(item)}"
        for item in archers
    ] or ["هنوز کمانداری ندارید."]
    lines += ["", "موجودی تیر:"]
    lines += [
        f"{item.pack.name}: {item.quantity} تیر، قدرت {item.pack.power}{' (انتخاب‌شده)' if item.is_equipped else ''}"
        for item in arrows
    ] or ["تیر موجود نیست."]
    await message.answer(
        "\n".join(lines),
        reply_markup=keyboard(
            [
                [button("خرید کماندار", "archers", icon=ARCHER_ICON)],
                [button("پک تیر کماندار", "packs", icon=ARROW_ICON)],
                [button("انتخاب تیر دفاعی", "equip", icon=ARROW_ICON)],
                [button("کماندارهای من و ارتقا", "owned", icon=ARCHER_ICON)],
            ]
        ),
    )


@router.message(F.chat.type == "private", F.text.in_({"کماندار ها", "کماندارها"}))
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
        if action == "menu":
            await show_menu(callback.message, session, user.id)
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
            rows.append([button("بازگشت", "menu")])
            await callback.message.answer(
                "🏹 خرید کماندار؛ هر فرمانده فقط یک کماندار دارد.",
                reply_markup=keyboard(rows),
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
            rows.append([button("بازگشت", "menu")])
            await callback.message.answer(
                "🎯 پک‌های تیر؛ هر دبیر مهاجم حداکثر یک تیر می‌خورد.",
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
            rows.append([button("بازگشت", "menu")])
            await callback.message.answer(
                "کماندارهای شما:", reply_markup=keyboard(rows)
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
                rows.append([button("بازگشت", "menu")])
                await callback.message.answer(
                    "تیر انتخاب‌شده برای هر دبیر مهاجم یک‌بار مصرف می‌شود. وقتی تمام شد، نوع دیگری را انتخاب کنید.",
                    reply_markup=keyboard(rows),
                )
            else:
                item = await service.equip_pack(session, user.id, callback_data.item_id)
                await session.commit()
                await callback.message.answer(
                    f"🎯 تیر {item.pack.name} برای دفاع انتخاب شد."
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
            await callback.message.answer(
                f"🏹 خرید {item.name}\nقدرت پایه: {item.power}\nسطح بازشدن: {item.unlock_level}\nقیمت: {item.purchase_price} {'الماس' if item.purchase_resource is ResourceType.DIAMOND else 'طلا'}\n\nخرید را تأیید می‌کنید؟",
                reply_markup=keyboard(
                    [
                        [
                            button("✅ تأیید خرید", "confirm_archer", item.id),
                            button("❌ لغو", "archers"),
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
            await callback.message.answer(
                f"🎯 خرید {item.name}\nتعداد: {item.quantity} تیر\nقدرت هر تیر: {item.power}\nسطح بازشدن: {item.unlock_level}\nقیمت: {item.purchase_price} {'الماس' if item.purchase_resource is ResourceType.DIAMOND else 'طلا'}\n\nخرید را تأیید می‌کنید؟",
                reply_markup=keyboard(
                    [
                        [
                            button("✅ تأیید خرید", "confirm_pack", item.id),
                            button("❌ لغو", "packs"),
                        ]
                    ]
                ),
            )
        elif action == "confirm_archer":
            item = await service.buy_archer(session, user.id, callback_data.item_id)
            await session.commit()
            await callback.message.answer(
                f"🏹 کماندار {item.archer.name} خریداری شد. قدرت: {service.power(item)}"
            )
        elif action == "confirm_pack":
            item = await service.buy_pack(session, user.id, callback_data.item_id)
            await session.commit()
            await callback.message.answer(
                f"🎯 پک {item.pack.name} خریداری شد. موجودی: {item.quantity} تیر"
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
            await callback.message.answer(
                f"🏹 ارتقای {item.archer.name} به سطح {item.level + 1}\nقدرت جدید: {item.archer.power + item.level * max(1, ceil(item.archer.power * 0.08))}\nهزینه: {service.upgrade_cost(item)} الماس\n\nارتقا را تأیید می‌کنید؟",
                reply_markup=keyboard(
                    [
                        [
                            button("✅ تأیید ارتقا", "confirm_upgrade", item.id),
                            button("❌ لغو", "owned"),
                        ]
                    ]
                ),
            )
        elif action == "confirm_upgrade":
            item = await service.upgrade(session, user.id, callback_data.item_id)
            await session.commit()
            await callback.message.answer(
                f"🏹 {item.archer.name} به سطح {item.level} رسید. قدرت جدید: {service.power(item)}"
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
            await callback.message.answer(
                f"فروش کماندار {item.archer.name}؟\n{item.archer.purchase_price // 2} {'الماس' if item.archer.purchase_resource is ResourceType.DIAMOND else 'طلا'} بازمی‌گردد. هزینهٔ ارتقا بازپرداخت نمی‌شود.",
                reply_markup=keyboard(
                    [
                        [
                            button("✅ تأیید فروش", "confirm_sell", item.id),
                            button("❌ لغو", "owned"),
                        ]
                    ]
                ),
            )
        elif action == "confirm_sell":
            name, refund, currency = await service.sell(
                session, user.id, callback_data.item_id
            )
            await session.commit()
            await callback.message.answer(
                f"🏹 کماندار {name} فروخته شد. {refund} {'الماس' if currency is ResourceType.DIAMOND else 'طلا'} بازگشت."
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
