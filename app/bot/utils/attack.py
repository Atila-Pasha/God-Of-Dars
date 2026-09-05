from __future__ import annotations


def teacher_phrase(teacher_names: str) -> str:
    names = [name.strip() for name in teacher_names.split("،") if name.strip()]
    if len(names) == 1:
        return f"دبیر {names[0]}"
    return f"دبیر های {' '.join(names)}"
