"""Resolve group teacher names without silently choosing an ambiguous surname."""

from collections.abc import Iterable

from app.models.teacher import Teacher


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
