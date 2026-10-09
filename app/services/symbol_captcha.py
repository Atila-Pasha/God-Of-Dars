"""Picture challenge for group chance boxes."""

from __future__ import annotations

import secrets
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


def make_symbol_captcha() -> tuple[bytes, str, tuple[str, ...]]:
    """Return a numbered 3×3 grid with one pair of swords among shields."""
    answer = secrets.randbelow(9) + 1
    image = Image.new("RGB", (720, 720), "#101d32")
    draw = ImageDraw.Draw(image)
    number_font = ImageFont.load_default(size=32)

    for index in range(9):
        column, row = index % 3, index // 3
        x, y = 48 + column * 218, 48 + row * 218
        draw.rounded_rectangle((x, y, x + 188, y + 188), radius=26, fill="#203149")
        draw.rounded_rectangle(
            (x + 2, y + 2, x + 186, y + 186),
            radius=24,
            outline="#38516d",
            width=3,
        )
        draw.text((x + 19, y + 14), str(index + 1), font=number_font, fill="#aabbd0")
        if index + 1 == answer:
            _draw_swords(draw, x + 94, y + 105)
        else:
            _draw_shield(draw, x + 94, y + 105)

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue(), str(answer), tuple(str(i) for i in range(1, 10))


def _draw_shield(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    outline = [
        (cx - 55, cy - 64),
        (cx, cy - 78),
        (cx + 55, cy - 64),
        (cx + 51, cy + 8),
        (cx + 35, cy + 42),
        (cx, cy + 68),
        (cx - 35, cy + 42),
        (cx - 51, cy + 8),
    ]
    inset = [
        (cx - 45, cy - 55),
        (cx, cy - 67),
        (cx + 45, cy - 55),
        (cx + 42, cy + 4),
        (cx + 28, cy + 34),
        (cx, cy + 55),
        (cx - 28, cy + 34),
        (cx - 42, cy + 4),
    ]
    draw.polygon(outline, fill="#9fb8cd")
    draw.polygon(inset, fill="#4187ae")
    draw.polygon(
        [
            (cx, cy - 67),
            (cx + 45, cy - 55),
            (cx + 42, cy + 4),
            (cx + 28, cy + 34),
            (cx, cy + 55),
        ],
        fill="#316b98",
    )
    draw.line((cx, cy - 62, cx, cy + 47), fill="#acd3e5", width=5)


def _draw_swords(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    """Draw two clearly crossed swords, including hilts and pommels."""
    for direction in (-1, 1):
        # Each sword runs from the lower outer corner to the upper opposite corner.
        tip = (cx - direction * 54, cy - 69)
        neck = (cx - direction * 42, cy - 39)
        hilt = (cx + direction * 34, cy + 42)
        pommel = (cx + direction * 59, cy + 68)
        draw.line((neck, hilt), fill="#dce8ec", width=15)
        draw.polygon(
            [tip, (neck[0] - 8, neck[1]), (neck[0] + 8, neck[1])],
            fill="#f4f7ef",
        )
        draw.line(
            (cx + direction * 17, cy + 23, cx + direction * 49, cy + 21),
            fill="#e8ba5a",
            width=12,
        )
        draw.line((hilt, pommel), fill="#b2733e", width=13)
        draw.ellipse(
            (pommel[0] - 8, pommel[1] - 8, pommel[0] + 8, pommel[1] + 8),
            fill="#e8ba5a",
        )
