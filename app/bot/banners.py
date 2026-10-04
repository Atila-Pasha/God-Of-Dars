"""MarkdownV2 banners for teacher purchases and attacks."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.bot.custom_emojis import CUSTOM_EMOJI_IDS, premium_emoji_id

if TYPE_CHECKING:
    from app.models.teacher import Teacher
    from app.services.attack_service import AttackPreview, AttackResult

MARKDOWN_V2 = "MarkdownV2"
_SPECIAL = re.compile(r"([\\_*\[\]()~`>#+\-=|{}.!])")


def escape(value: object) -> str:
    return _SPECIAL.sub(r"\\\1", str(value))


def bold(value: object) -> str:
    return f"*{escape(value)}*"


def emoji(emoji_id: str, fallback: str) -> str:
    return f"![{fallback}](tg://emoji?id={emoji_id})"


def rich_plain(value: str) -> str:
    """Escape ordinary text while replacing known emoji with custom entities."""
    icons = sorted(CUSTOM_EMOJI_IDS, key=len, reverse=True)
    parts: list[str] = []
    position = 0
    while position < len(value):
        icon = next((item for item in icons if value.startswith(item, position)), None)
        if icon is None:
            parts.append(escape(value[position]))
            position += 1
        else:
            parts.append(emoji(CUSTOM_EMOJI_IDS[icon], icon))
            position += len(icon)
    return "".join(parts)


_DIVIDER = re.compile(r"^[.\s]*[─━═ـ┼│]{5,}[.\s]*$")


def _banner_line(value: str, *, heading: bool = False) -> str:
    indentation = value[: len(value) - len(value.lstrip())]
    content = value.strip()
    icon = next(
        (
            item
            for item in sorted(CUSTOM_EMOJI_IDS, key=len, reverse=True)
            if content.startswith(item)
        ),
        None,
    )
    prefix = f"{emoji(CUSTOM_EMOJI_IDS[icon], icon)} " if icon else ""
    body = content[len(icon) :].strip() if icon else content
    if not body:
        return escape(indentation) + prefix.rstrip()
    if heading:
        rendered = bold(body)
    elif ":" in body and "://" not in body and body.index(":") <= 35:
        label, detail = body.split(":", 1)
        rendered = f"{bold(label + ':')} {rich_plain(detail.strip())}"
    else:
        rendered = rich_plain(body)
    return escape(indentation) + prefix + rendered


def rich_banner(value: str) -> str:
    """Give plain bot banners a consistent MarkdownV2 layout."""
    source = [
        line.rstrip() for line in value.splitlines() if not _DIVIDER.fullmatch(line)
    ]
    while source and not source[0].strip():
        source.pop(0)
    while source and not source[-1].strip():
        source.pop()
    if not source:
        return ""
    lines = [_banner_line(source[0], heading=True)]
    blanks = 0
    for line in source[1:]:
        if not line.strip():
            blanks += 1
            if blanks <= 1:
                lines.append("")
            continue
        is_subheading = (
            blanks > 0
            and any(line.strip().startswith(icon) for icon in CUSTOM_EMOJI_IDS)
            and ":" not in line
            and len(line.strip()) <= 52
        )
        blanks = 0
        lines.append(_banner_line(line, heading=is_subheading))
    return "\n".join(lines)


def _short(value: str, limit: int = 180) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 1] + "…"


def teacher_icon(value: str | None) -> str:
    fallback = value if value and not value.isdecimal() else "👨‍🏫"
    emoji_id = premium_emoji_id(value) or premium_emoji_id("👨‍🏫")
    return emoji(emoji_id, fallback) if emoji_id else fallback


SWORD = emoji("5823192436024813346", "⚔️")
TARGET = emoji("6032949275732742941", "🎯")
FORCES = emoji("5825822115651133329", "👨‍🏫")
DEFENSE = emoji("5825861861278490879", "🛡️")
INJURY = emoji("5213455977919039650", "🩸")
LOOT = emoji("5825832256068918886", "🎁")
COIN = emoji("5825699971076202989", "🪙")
BANANA = emoji("5902520589356113908", "🍌")
DIAMOND = emoji("5825753314570018832", "💎")
QUESTION = emoji("5935912783261470019", "❓")
CONFIRM = emoji("5823388325188214894", "✅")
FINISH = emoji("5825727141039317043", "🏰")
REPORT = emoji("5825627287344651886", "📜")
TEACHERS = emoji("5825625629487276345", "👨‍🏫")
DAMAGE = emoji("5276032951342088188", "💥")
CASTLE = emoji("5823403314624080082", "🏰")
HEAL = emoji("5825570280243732195", "🩹")
STAR = emoji("5825647731388981287", "⭐")
SPARKLE = emoji("5825920844064366385", "✨")
ENTRY = emoji("5825709849500985213", "✅")
LAUNCH = emoji("5847957479446547693", "🚀")
SCHOOL = emoji("5825545274944135130", "🏫")
LEVEL = emoji("5825727141039317043", "🎖️")
UNLOCK = emoji("5823611946955447648", "✨")
FORT = emoji("5825546447470206916", "🏰")


def section_entry_banner(name: str) -> str:
    return f"{ENTRY} {bold(f'وارد بخش {name} شدید')}\\."


def attack_launch_banner(
    target_name: str,
    teacher_details: tuple[tuple[str, str | None, str | None], ...],
    *,
    remaining_seconds: int | None = None,
) -> str:
    teachers = "\n\n".join(
        f"《 {escape(name)}  {teacher_icon(icon)}》"
        for name, _ability, icon in teacher_details[:4]
    )
    footer = (
        "پس از پایان زمان، نتیجه حمله برای شما ارسال می‌شود\\."
        if remaining_seconds is None
        else f"زمان باقی‌مانده تا تکمیل حمله: {escape(f'{remaining_seconds // 60:02d}:{remaining_seconds % 60:02d}')}"
    )
    return (
        f"{LAUNCH} {bold(f'حمله به «{target_name}» آغاز شد!')}\n\n"
        f"{TEACHERS} دبیر :\n{teachers}\n\n{footer}"
    )


def purchase_banner(teacher: Teacher) -> str:
    resource = getattr(teacher.purchase_resource, "value", teacher.purchase_resource)
    currency = "الماس" if resource == "DIAMOND" else "طلا"
    currency_icon = DIAMOND if currency == "الماس" else COIN
    ability = (
        _short(str(teacher.ability_text or "توانایی ویژه‌ای ثبت نشده"))
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("\\", "\\\\")
        .replace("`", r"\`")
    )
    return (
        f"{teacher_icon(teacher.emoji)}    خرید دبیر «{bold(teacher.name)}»\n\n"
        f"● توانایی دبیر: `﹙{ability}﹚`\n\n"
        f"{currency_icon} {bold('قیمت')}: {escape(teacher.purchase_price)} {escape(currency)}\n"
        f"> سطح بازشدن: {escape(teacher.unlock_level)}\n\n"
        f"{CONFIRM} {bold('آیا خرید این دبیر را تأیید می‌کنید؟')}"
    )


def _teacher_lines(
    details: tuple[tuple[str, str | None, str | None], ...],
    fallback_name: str,
    fallback_emojis: tuple[str | None, ...] = (),
) -> list[str]:
    if not details:
        names = [name.strip() for name in fallback_name.split("،") if name.strip()]
        details = tuple(
            (
                name,
                None,
                fallback_emojis[index] if index < len(fallback_emojis) else None,
            )
            for index, name in enumerate(names)
        )
    return [
        f"{teacher_icon(icon)}{bold(name)}\n\n"
        f"{SPARKLE} توانایی دبیر: {escape(_short(ability or 'ثبت نشده'))}"
        for name, ability, icon in details[:4]
    ]


def attack_preview_banner(preview: AttackPreview) -> str:
    details = _teacher_lines(
        preview.teacher_details, preview.teacher_name, preview.teacher_emojis
    )
    return (
        f"{SWORD} {bold('قربان! به این موارد توجه کنید:')}\n\n"
        f"{TARGET} هدف: {bold(preview.target_name)}\n\n"
        f"{FORCES} نیروهای تنظیم‌شده:\n\n" + "\n\n".join(details) + "\n\n"
        f"{DEFENSE} دفاع دژ:\n"
        f"> {escape(preview.defense_power)} DMG {DEFENSE}\n\n"
        f"{INJURY} آسیب احتمالی دبیر:\n"
        f"> {escape(preview.estimated_teacher_injury)} HP {INJURY}\n\n"
        f"{LOOT} {bold('غنیمت')} احتمالی از منابع حریف:\n"
        f"{COIN}    {bold('طلا')}: {escape(preview.loot_coin)}\n"
        f"{BANANA}    {bold('موز')}: {escape(preview.loot_banana)}\n\n"
        f"{QUESTION} {bold('فرمان حمله رو صادر می‌کنی؟')}"
    )


def attack_result_banner(result: AttackResult, *, recipient: str = "attacker") -> str:
    before = result.castle_strength_before or (
        result.castle_strength_after + result.castle_damage
    )
    percent = min(100, round(result.castle_damage * 100 / before)) if before > 0 else 0
    if result.blocked_by_shield:
        outcome = "سپر دفاعی حمله را خنثی کرد؛ دژ سالم ماند."
    elif percent >= 100:
        outcome = (
            "نیروها قلعهٔ دشمن را فتح کردند!"
            if recipient != "defender"
            else "دژت سقوط کرد؛ برای نبرد بعدی بازسازی‌اش کن."
        )
    elif percent >= 50:
        outcome = (
            "ضربهٔ سنگینی به دژ وارد شد."
            if recipient != "defender"
            else "دژت آسیب سنگینی دید؛ دفاعت را تقویت کن."
        )
    elif percent > 0:
        outcome = (
            "بخشی از دژ دشمن تخریب شد."
            if recipient != "defender"
            else "دژت آسیب دید، اما هنوز پابرجاست."
        )
    else:
        outcome = (
            "دژ دشمن مقاومت کرد."
            if recipient != "defender"
            else "دژت این حمله را دفع کرد."
        )
    headline = (
        f"به قلعهٔ تو از طرف «{result.attacker_name}» حمله شد!"
        if recipient == "defender"
        else f"حمله به قلعهٔ «{result.target_name}» تمام شد!"
    )
    teacher_lines = "  ".join(
        f"《{teacher_icon(icon)} {escape(name)}》"
        for name, _ability, icon in (
            result.teacher_details
            or tuple(
                (name.strip(), None, None) for name in result.teacher_name.split("،")
            )
        )[:4]
        if name
    )
    closing = (
        f"دژت را ترمیم کن، فرمانده {STAR}"
        if recipient == "defender"
        else f"“Keep going, commander\\.” {STAR}"
    )
    loot_label = "منابع ازدست‌رفته" if recipient == "defender" else "غنیمت‌های کسب‌شده"
    return (
        f"{FINISH} {bold(headline)} {FINISH}\n\n"
        f"{REPORT} {bold('گزارش نتیجهٔ نبرد:')}\n"
        f"{escape(outcome)} {FORCES}\n"
        f"● میزان تخریب: {bold(f'{percent}%')}\n\n"
        f"{TEACHERS} دبیرها:\n{teacher_lines}\n\n"
        f"{DAMAGE} تخریب واردشده به قلعه:\n"
        f"> {escape(result.castle_damage)} DMG {INJURY}\n\n"
        f"{CASTLE} قدرت باقی‌ماندهٔ دژ:\n"
        f"> {escape(result.castle_strength_after)} DMG {CASTLE}\n\n"
        f"{HEAL} آسیب واردشده به دبیر:\n"
        f"> {escape(result.teacher_injury)} HP {HEAL}\n\n"
        f"{LOOT} {loot_label}:\n"
        f"{COIN}    طلا: {escape(result.loot_coin)}\n"
        f"{DIAMOND}    الماس: {escape(result.loot_diamond)}\n"
        f"{BANANA}    موز: {escape(result.loot_banana)}\n\n"
        f"{closing}"
    )


def attack_teacher_injury_banner(result: AttackResult) -> str:
    lines = []
    for teacher in result.teacher_injuries:
        heading = (
            f"{teacher_icon(teacher.emoji)} {escape(teacher.name)}: "
            f"{bold(f'{teacher.damage} HP')} آسیب دید\\."
        )
        if teacher.lost:
            status = "> 《 دبیرت را در نبرد از دست دادی و دیگر در تیمت نیست\\. 》"
        else:
            status = f"> 《 جان باقی‌مانده: {bold(f'{teacher.remaining_hp} HP')} 》"
        lines.append(f"{heading}\n\n{status}")
    if not lines:
        lines.append("اطلاعات آسیب دبیرها در دسترس نیست\\.")
    return (
        f"{HEAL} {bold('گزارش آسیب دبیرها')}\n\n"
        + "\n\n".join(lines)
        + f"\n\nLet’s go to the hospital\\. {INJURY}"
    )
