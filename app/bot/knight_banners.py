"""MarkdownV2 banners for the knight guard."""

from app.bot.archer_banners import (
    CHECK,
    COST,
    FORBIDDEN,
    UPGRADE,
    plain_price,
    price,
    quote,
)
from app.bot.banners import bold, emoji, escape, rich_plain
from app.core.enums import ResourceType
from app.models.knight import Knight, UserKnight
from app.services.knight_service import KnightService

KNIGHT = "5372804525935567057"
SWORD = "5825961702088254236"


def name(value: str, icon: str | None = None) -> str:
    displayed_icon = (
        emoji(icon, "⚔️")
        if icon and icon.isdigit()
        else rich_plain(icon)
        if icon
        else emoji(KNIGHT, "⚔️")
    )
    return f"{displayed_icon} {bold(value)}"


def school_overview(owned: UserKnight | None) -> str:
    if owned is None:
        detail = escape("هنوز شوالیه‌ای نداری.")
    else:
        power = KnightService.power(owned)
        reduction = min(40, power * 2)
        detail = f"{name(owned.knight.name, owned.knight.emoji)}\n" + quote(
            f"{escape('وضعیت:')} {escape('فعال' if owned.is_equipped and owned.current_hp else 'غیرفعال')}",
            f"{escape('سطح:')} {escape(owned.level)}",
            f"{escape('جان:')} {escape(owned.current_hp)} / {escape(KnightService.max_hp(owned))} HP",
            f"{escape('قدرت شمشیر:')} {escape(power)} DMG {emoji(SWORD, '⚔️')}",
            f"{escape('کاهش تخریب دژ و غارت منابع:')} {escape(reduction)}٪",
        )
    return (
        f"{emoji(KNIGHT, '⚔️')} {bold('شوالیهٔ دژ')}\n\n{detail}\n\n"
        + quote(
            escape(
                "شوالیهٔ فعال به دبیرهای مهاجم ضربه می‌زند و با هر دفاع جان از دست می‌دهد. اگر جانش صفر شود، می‌میرد و از مدرسه حذف می‌شود."
            )
        )
        + f"\n\n{escape('خرید شوالیه از بوفه ← دفاع دژ.')}"
    )


def buffet_entry() -> str:
    return f"{emoji(KNIGHT, '⚔️')} {bold('خرید شوالیه')}\n\n" + quote(
        escape(
            "شوالیه بدون تیر از دژ دفاع می‌کند. قدرتش به دبیرهای مهاجم آسیب می‌زند و درصد تخریب و غارت را کم می‌کند. جانش درمان نمی‌شود و با رسیدن به صفر برای همیشه از دست می‌رود."
        )
    )


def catalog() -> str:
    return f"{emoji(KNIGHT, '⚔️')} {bold('فهرست شوالیه‌ها')}\n" + quote(
        escape(
            "هر فرمانده یک شوالیه می‌تواند داشته باشد. برای تعویض، شوالیهٔ قبلی را بفروشید؛ شوالیهٔ مرده خودکار از مدرسه حذف می‌شود."
        )
    )


def purchase(item: Knight) -> str:
    reduction = min(40, item.power * 2)
    return (
        f"{emoji(KNIGHT, '⚔️')} {bold('خرید شوالیه')} « {name(item.name, item.emoji)} »\n\n"
        + quote(
            f"{escape('قدرت پایه:')} {escape(item.power)} DMG {emoji(SWORD, '⚔️')}",
            f"{escape('جان:')} {escape(item.max_hp)} HP",
            f"{escape('کاهش تخریب و غارت:')} {escape(reduction)}٪",
            f"{escape('سطح بازشدن:')} {escape(item.unlock_level)}",
            f"{escape('قیمت:')} {price(item.purchase_price, item.purchase_resource)}",
        )
        + f"\n\n{escape('جان شوالیه درمان نمی‌شود و در جان صفر از دست می‌رود. خرید را تأیید می‌کنید؟')}"
    )


def bought(item: UserKnight) -> str:
    return (
        f"{emoji(CHECK, '✔️')} {escape('شوالیه')} « {name(item.knight.name, item.knight.emoji)} » {escape('خریداری شد.')}\n"
        + quote(
            f"{escape('جان:')} {escape(item.current_hp)} HP",
            escape("برای تغییر نگهبان فعال، از مدرسه من استفاده کنید."),
        )
    )


def upgrade_preview(item: UserKnight) -> str:
    return f"{emoji(UPGRADE, '⬆️')} {escape('ارتقای شوالیه')} « {name(item.knight.name, item.knight.emoji)} » {escape('به سطح')} {escape(item.level + 1)}\n\n{emoji(COST, '💰')} {escape('هزینه:')} {price(KnightService.upgrade_cost(item), ResourceType.DIAMOND)}\n\n{escape('ارتقا فقط سقف جان و قدرت را زیاد می‌کند؛ جان ازدست‌رفته برنمی‌گردد. تأیید می‌کنید؟')}"


def sell_preview(item: UserKnight) -> str:
    return (
        f"{emoji(FORBIDDEN, '🚫')} {escape('فروش شوالیه')} « {name(item.knight.name, item.knight.emoji)} »\n"
        + quote(
            f"{plain_price(item.knight.purchase_price // 2, item.knight.purchase_resource)} {escape('باز می‌گردد.')}",
            escape("هزینهٔ ارتقا بازپرداخت نمی‌شود."),
        )
    )
