"""MarkdownV2 copy for the archer pages in school and the buffet."""

from math import ceil

from app.bot.banners import bold, emoji, escape, rich_plain
from app.core.enums import ResourceType
from app.models.archer import Archer, ArrowPack, UserArcher, UserArrow

BOW = "5314526780416092636"
ARCHER = "6034940654499400541"
TARGET = "5924618767324681321"
RABBIT = "5395457261491470895"
DEFENSE = "5230967066390980139"
BUFFET = "5823511728188563725"
FORBIDDEN = "5823388325188214894"
GOLD = "5825699971076202989"
UPGRADE = "5866060208253441223"
COST = "5866369239740320716"
DIAMOND = "5825753314570018832"
SHOP = "6136165122336362571"
CHECK = "5825709849500985213"


def quote(*lines: str) -> str:
    """Build a Telegram MarkdownV2 blockquote from escaped/markup lines."""
    return "\n".join(f">{line}" for line in lines)


def archer_icon(value: str | None) -> str:
    if value and value.isdigit():
        return emoji(value, "🏹")
    return rich_plain(value or "🏹")


def archer_name(name: str, icon: str | None = None, *, quoted: bool = False) -> str:
    rendered = f"{archer_icon(icon)} {bold(name)}"
    return f"« {rendered} »" if quoted else rendered


def price(amount: int, currency: ResourceType) -> str:
    if currency is ResourceType.DIAMOND:
        return f"{escape(amount)} الماس {emoji(DIAMOND, '💎')}"
    return f"{escape(amount)} طلا {emoji(GOLD, '🥇')}"


def plain_price(amount: int, currency: ResourceType) -> str:
    unit = "الماس" if currency is ResourceType.DIAMOND else "طلا"
    return f"{escape(amount)} {unit}"


def school_overview(
    owned: UserArcher | None, arrows: list[UserArrow], power: int
) -> str:
    if owned:
        archer_section = (
            f"{emoji(ARCHER, '🏹')} کماندار: {archer_name(owned.archer.name, owned.archer.emoji)}\n\n"
            f"● وضعیت: {escape('فعال' if getattr(owned, 'is_equipped', True) else 'غیرفعال')}\n"
            f"● سطح: {escape(owned.level)}\n"
            f"● قدرت:\n{quote(f'{escape(power)} DMG {emoji(TARGET, "🎯")}')}"
        )
    else:
        archer_section = escape("هنوز کمانداری نداری.")
    stock_lines = [
        f"{escape(stock.pack.name)}: {escape(stock.quantity)} تیر، قدرت {escape(stock.pack.power)}"
        + (f" {escape('(انتخاب‌شده)')}" if stock.is_equipped else "")
        for stock in arrows
    ]
    inventory = (
        quote(*stock_lines) if stock_lines else quote(escape("تیری در انبار نیست."))
    )
    return (
        f"{emoji(BOW, '🏹')} {bold('کماندار دژ')}\n\n"
        f"{archer_section}\n\n"
        f"{emoji(RABBIT, '🐇')} {bold('موجودی تیر')}\n{inventory}\n\n"
        f"{emoji(DEFENSE, '🏹')} {escape('هر دبیر مهاجم، یک تیر از نوع انتخاب‌شده می‌خورد. ارتقا، فروش و انتخاب تیر از همین بخش انجام می‌شود.')}\n\n"
        f"{escape('برای خرید «کماندار و پک تیر» به بوفه')} {emoji(BUFFET, '🎁')} {escape('برو.')}"
    )


def buffet_entry() -> str:
    return (
        f"{emoji(SHOP, '💞')} {bold('دفاع دژ')}\n\n"
        + quote(
            escape(
                "کماندار با تیر و شوالیه با شمشیر از دژ دفاع می‌کنند. تیر کماندار را جداگانه تهیه کن؛ شوالیه تیر مصرف نمی‌کند و با صفرشدن جانش از دست می‌رود."
            )
        )
        + "\n\n"
        + f"● {escape('هم‌زمان فقط یک نگهبان فعال است.')}\n"
        + escape("ارتقا، فروش و انتخاب نگهبان از «مدرسه من» انجام می‌شود.")
    )


def archer_catalog() -> str:
    return f"{emoji(BOW, '🏹')} {bold('خرید کماندار')}\n" + quote(
        escape(
            "هر فرمانده فقط یک کماندار دارد. برای تعویض، کماندار فعلی را در مدرسه بفروشید."
        )
    )


def owned_catalog(owned: list[UserArcher]) -> str:
    details = [
        f"{archer_name(item.archer.name, item.archer.emoji)}، {escape('سطح')} {escape(item.level)}"
        for item in owned
    ] or [escape("هنوز کمانداری نداری.")]
    return f"{emoji(BOW, '🏹')} {bold('کماندار من')}\n" + quote(*details)


def pack_catalog() -> str:
    return f"{emoji(RABBIT, '🐇')} {bold('پک‌های تیر؛')}\n" + quote(
        escape("هر دبیر مهاجم، حداکثر یک تیر می‌خورد.")
    )


def archer_purchase(item: Archer) -> str:
    return (
        f"{emoji(ARCHER, '🏹')} {bold('خرید کماندار')} {archer_name(item.name, item.emoji, quoted=True)}\n\n"
        + quote(
            f"{escape('قدرت پایه:')} {escape(item.power)} DMG {emoji(TARGET, '🎯')}",
            f"{escape('سطح بازشدن:')} {escape(item.unlock_level)}",
            f"{escape('قیمت:')} {price(item.purchase_price, item.purchase_resource)}",
        )
        + f"\n\n{escape('خرید را تأیید می‌کنید؟')}"
    )


def pack_purchase(item: ArrowPack) -> str:
    return (
        f"{emoji(RABBIT, '🐇')} {bold('خرید پک تیر')} « {bold(item.name)} »\n\n"
        + quote(
            f"{escape('تعداد:')} {escape(item.quantity)} {escape('تیر')}",
            f"{escape('قدرت هر تیر:')} {escape(item.power)} DMG {emoji(TARGET, '🎯')}",
            f"{escape('سطح بازشدن:')} {escape(item.unlock_level)}",
            f"{escape('قیمت:')} {price(item.purchase_price, item.purchase_resource)}",
        )
        + f"\n\n{escape('خرید را تأیید می‌کنید؟')}"
    )


def archer_bought(item: UserArcher, power: int) -> str:
    return (
        f"{emoji(CHECK, '✔️')} کماندار {archer_name(item.archer.name, item.archer.emoji, quoted=True)} {escape('خریداری شد.')}\n"
        + quote(f"{escape('قدرت:')} {escape(power)} DMG {emoji(TARGET, '🎯')}")
    )


def pack_bought(item: UserArrow) -> str:
    return (
        f"{emoji(CHECK, '✔️')} پک تیر « {bold(item.pack.name)} » {escape('خریداری شد.')}\n"
        + quote(f"{escape('موجودی:')} {escape(item.quantity)} {escape('تیر')}")
    )


def upgrade_preview(item: UserArcher, cost: int) -> str:
    next_power = item.archer.power + item.level * max(1, ceil(item.archer.power * 0.08))
    return (
        f"{emoji(UPGRADE, '⬆️')} {escape('ارتقای')} {archer_name(item.archer.name, item.archer.emoji, quoted=True)} {escape('به سطح')} {escape(item.level + 1)}\n\n"
        f"● {escape('قدرت جدید:')}\n"
        + quote(f"{escape(next_power)} DMG {emoji(TARGET, '🎯')}")
        + f"\n\n{emoji(COST, '💰')} {escape('هزینه:')} {price(cost, ResourceType.DIAMOND)}\n\n"
        + escape("آیا ارتقا را تأیید می‌کنید؟")
    )


def upgrade_done(item: UserArcher, power: int) -> str:
    return (
        f"{emoji(CHECK, '✔️')} {archer_name(item.archer.name, item.archer.emoji, quoted=True)} {escape('به سطح')} {escape(item.level)} {escape('رسید.')}\n"
        + quote(f"{escape('قدرت جدید:')} {escape(power)} DMG {emoji(TARGET, '🎯')}")
    )


def sell_preview(item: UserArcher) -> str:
    return (
        f"{emoji(FORBIDDEN, '🚫')} {escape('آیا از فروش کماندار')} {archer_name(item.archer.name, item.archer.emoji, quoted=True)} {escape('اطمینان دارید؟')}\n\n"
        + quote(
            f"{plain_price(item.archer.purchase_price // 2, item.archer.purchase_resource)} {escape('باز می‌گردد.')}",
            escape("هزینهٔ ارتقا بازپرداخت نمی‌شود."),
        )
    )


def sell_done(name: str, refund: int, currency: ResourceType) -> str:
    return (
        f"{emoji(CHECK, '✔️')} {escape('کماندار')} « {bold(name)} » {escape('فروخته شد.')}\n"
        + quote(f"{plain_price(refund, currency)} {escape('بازگشت.')}")
    )


def ammo_selection() -> str:
    return f"{emoji(RABBIT, '🐇')} {bold('انتخاب تیر دفاعی')}\n" + quote(
        escape(
            "هر تیر برای یک دبیر مهاجم مصرف می‌شود. وقتی موجودی تمام شد، نوع دیگری را انتخاب کنید."
        )
    )


def ammo_equipped(name: str) -> str:
    return f"{emoji(CHECK, '✔️')} {escape('تیر')} « {bold(name)} » {escape('برای دفاع انتخاب شد.')}"
