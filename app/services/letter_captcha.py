"""Readable letter captcha used only by group chance boxes."""

from __future__ import annotations

import secrets
import struct
import zlib

_ALPHABET = "ACEFHKMNPRTUXY"
_GLYPHS = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
}


def _png_letters(answer: str) -> bytes:
    scale = 12
    width = (len(answer) * 7 - 2) * scale + 24
    height = 7 * scale + 24
    background = b"\x13\x22\x34"
    foreground = b"\xf3\xf8\xff"
    rows = [bytearray(b"\x00" + background * width) for _ in range(height)]
    for index, char in enumerate(answer):
        for gy, line in enumerate(_GLYPHS[char]):
            for gx, bit in enumerate(line):
                if bit != "1":
                    continue
                start_x = 12 + (index * 7 + gx) * scale
                start_y = 12 + gy * scale
                for y in range(start_y, start_y + scale):
                    offset = 1 + start_x * 3
                    rows[y][offset : offset + scale * 3] = foreground * scale

    def chunk(kind: bytes, value: bytes) -> bytes:
        return (
            struct.pack(">I", len(value))
            + kind
            + value
            + struct.pack(">I", zlib.crc32(kind + value) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )


def make_letter_captcha() -> tuple[bytes, str, tuple[str, str, str]]:
    answer = "".join(secrets.choice(_ALPHABET) for _ in range(4))
    choices = {answer}
    while len(choices) < 3:
        index = secrets.randbelow(4)
        replacement = secrets.choice(_ALPHABET.replace(answer[index], ""))
        choices.add(answer[:index] + replacement + answer[index + 1 :])
    options = list(choices)
    secrets.SystemRandom().shuffle(options)
    return _png_letters(answer), answer, tuple(options)
