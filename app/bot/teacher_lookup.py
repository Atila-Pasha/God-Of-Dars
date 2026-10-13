"""Resolve group teacher names without silently choosing an ambiguous surname."""

import re
from collections.abc import Iterable

from app.models.teacher import Teacher

BUYABLE_TEACHERS_QUERY = re.compile(
    r"^\s*(?:دبیر[\s\u200c]*های\s+مجاز|چه\s+دبیر[\s\u200c]*هایی\s+رو\s+می[\s\u200c]*تونم\s+بخرم)\s*[؟?]?\s*$"
)
TEACHER_STATUS_QUERY = re.compile(r"^\s*وضعیت\s+دبیر[\s\u200c]*ها\s*[؟?]?\s*$")


def _normalized(value: str) -> str:
    return " ".join(
        value.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ").split()
    ).casefold()


def matching_teachers(teachers: Iterable[Teacher], query: str) -> list[Teacher]:
    name = _normalized(query)
    if not name:
        return []
    catalog = list(teachers)
    exact = [teacher for teacher in catalog if _normalized(teacher.name) == name]
    if exact:
        return exact

    words = name.split()
    if len(words) == 1:
        return [
            teacher
            for teacher in catalog
            if _normalized(teacher.name).split()[-1] == name
        ]
    # Older catalogs sometimes store only the surname. Accept a supplied
    # full name when its surname is the complete catalog name.
    return [
        teacher
        for teacher in catalog
        if len(_normalized(teacher.name).split()) == 1
        and _normalized(teacher.name) == words[-1]
    ]
