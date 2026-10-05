"""Premium custom-emoji progress bars for Persian Telegram banners."""

from app.bot.banners import emoji

_EMPTY = ("5931534188657254206", "5933785859621920322", "5931275038920548077")
_FULL = ("5949744124142820550", "5949736114028814482", "5947346029153100052")
_PARTIAL = (
    ("5949346577674935537", "5949509477194537601", "5949308223616982431"),
    ("5947466314007192098", "5947256955826363081", "5949707002740481824"),
    ("5949257543002889576", "5949513969730330381", "5947323523524468309"),
)


def premium_progress_bar(
    value: int, maximum: int, *, width: int = 8, show_percent: bool = False
) -> str:
    """Fill a green bar from right to left, preserving the physical cell order."""
    width = max(2, width)
    maximum = max(1, maximum)
    fill = max(0.0, min(float(width), width * value / maximum))
    cells = []
    for index in range(width):
        kind = 0 if index == 0 else 2 if index == width - 1 else 1
        portion = max(0.0, min(1.0, fill - (width - 1 - index)))
        if portion <= 0:
            icon_id = _EMPTY[kind]
        elif portion >= 1:
            icon_id = _FULL[kind]
        else:
            icon_id = _PARTIAL[kind][min(2, int(portion * 3))]
        cells.append(emoji(icon_id, "▫️"))
    result = f"\u2066{''.join(cells)}\u2069"
    if show_percent:
        percent = min(100, max(0, value * 100 // maximum))
        result += f"  \u2066{percent}%\u2069"
    return result
