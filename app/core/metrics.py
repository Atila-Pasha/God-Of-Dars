from __future__ import annotations

from collections import Counter, deque
from time import monotonic

_counters: Counter[str] = Counter()
_latencies: dict[str, deque[float]] = {}
_MAX_SAMPLES = 2048


def increment(name: str, value: int = 1) -> None:
    _counters[name] += value


def observe(name: str, milliseconds: float) -> None:
    samples = _latencies.setdefault(name, deque(maxlen=_MAX_SAMPLES))
    samples.append(milliseconds)


def snapshot() -> dict[str, object]:
    return {
        "counters": dict(_counters),
        "latencies_ms": {
            name: {
                "count": len(values),
                "last": values[-1] if values else None,
                "max": max(values) if values else None,
            }
            for name, values in _latencies.items()
        },
    }


def timer(name: str):
    started = monotonic()

    def finish() -> None:
        observe(name, (monotonic() - started) * 1000)

    return finish
