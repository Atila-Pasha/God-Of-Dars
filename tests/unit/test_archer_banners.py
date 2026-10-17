from types import SimpleNamespace

from app.bot import archer_banners as banners
from app.core.enums import ResourceType


def _owned():
    archer = SimpleNamespace(
        name="محسنی (آزمایشی)",
        emoji="5314526780416092636",
        power=4,
        purchase_price=80,
        purchase_resource=ResourceType.COIN,
    )
    return SimpleNamespace(archer=archer, level=1)


def test_school_banner_uses_requested_icons_and_blockquotes() -> None:
    stock = SimpleNamespace(
        pack=SimpleNamespace(name="تیر ساده (آزمایشی)", power=2),
        quantity=2,
        is_equipped=True,
    )
    text = banners.school_overview(_owned(), [stock], 4)

    requested = (
        banners.BOW,
        banners.ARCHER,
        banners.TARGET,
        banners.RABBIT,
        banners.DEFENSE,
        banners.BUFFET,
    )
    assert all(
        text.index(icon) < text.index(next_icon)
        for icon, next_icon in zip(requested, requested[1:], strict=False)
    )
    assert ">4 DMG" in text
    assert ">تیر ساده \\(آزمایشی\\): 2 تیر، قدرت 2" in text
    assert "انتخاب‌شده" in text
    assert "برای خرید «کماندار و پک تیر»" in text


def test_sale_upgrade_and_shop_banners_use_requested_icons() -> None:
    owned = _owned()
    sale = banners.sell_preview(owned)
    upgrade = banners.upgrade_preview(owned, 2)
    shop = banners.buffet_entry()
    packs = banners.pack_catalog()
    bought = banners.archer_bought(owned, 4)

    assert sale.startswith(f"![🚫](tg://emoji?id={banners.FORBIDDEN})")
    assert f"![🥇](tg://emoji?id={banners.GOLD})" not in sale
    assert ">40 طلا" in sale
    assert f"![🥇](tg://emoji?id={banners.GOLD})" not in banners.sell_done(
        owned.archer.name, 40, ResourceType.COIN
    )
    assert ">هزینهٔ ارتقا بازپرداخت نمی‌شود" in sale
    for icon in (
        banners.UPGRADE,
        banners.TARGET,
        banners.COST,
        banners.DIAMOND,
    ):
        assert icon in upgrade
    assert ">5 DMG" in upgrade
    assert shop.startswith(f"![💞](tg://emoji?id={banners.SHOP})")
    assert ">کماندار با تیر و شوالیه با شمشیر" in shop
    assert packs.startswith(f"![🐇](tg://emoji?id={banners.RABBIT})")
    assert ">هر دبیر مهاجم" in packs
    assert bought.startswith(f"![✔️](tg://emoji?id={banners.CHECK})")
    assert "محسنی" in bought
