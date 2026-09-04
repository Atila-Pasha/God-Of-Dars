from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

MENU_SECTIONS = (
    ("مدرسه من", "school", "5825697157872623308"),
    ("کتابخانه", "library", "5825629907274703191"),
    ("بوفه", "buffet", "5823511728188563725"),
    ("معدن منابع", "mine", "5823474022670671455"),
    ("پروفایل", "profile", "5825647731388981287"),
    ("فعالیت‌های روزانه", "daily", "5825898080737697438"),
)

MENU_SECTION_KEYS = frozenset(section for _, section, _ in MENU_SECTIONS)
MENU_SECTION_BY_LABEL = {label: section for label, section, _ in MENU_SECTIONS}
MENU_SECTION_LABELS = frozenset(MENU_SECTION_BY_LABEL)
NON_SCHOOL_MENU_SECTION_LABELS = frozenset(
    label for label, section, _ in MENU_SECTIONS if section != "school"
)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    buttons = []
    for label, _, custom_emoji_id in MENU_SECTIONS:
        button = KeyboardButton(text=label)
        if custom_emoji_id:
            button.icon_custom_emoji_id = custom_emoji_id
        buttons.append(button)

    keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        is_persistent=False,
        resize_keyboard=True,
    )
