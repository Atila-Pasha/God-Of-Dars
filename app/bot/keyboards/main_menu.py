from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

MENU_SECTIONS = (
    ("مدرسه من", "school", "5265002646397285605"),
    ("کتابخانه", "library", "5445275347366989283"),
    ("بوفه", "buffet", "5859297284029681680"),
    ("معدن منابع", "mine", ""),
    ("حمله", "attack", "5408935401442267103"),
    ("پروفایل", "profile", "5249053508681883137"),
    ("دعوت دوستان", "referral", "5449800250032143374"),
    ("فعالیت‌های روزانه", "daily", "5314665117017718786"),
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
