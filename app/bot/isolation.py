"""Serialize a user's FSM updates without retaining a lock for every past user."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from aiogram.fsm.storage.base import BaseEventIsolation, StorageKey


@dataclass
class _Entry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class UserEventIsolation(BaseEventIsolation):
    def __init__(self) -> None:
        self._entries: dict[tuple[int, int], _Entry] = {}

    @asynccontextmanager
    async def lock(self, key: StorageKey) -> AsyncGenerator[None, None]:
        # Game resources belong to the user across both private and group chats.
        identity = (key.bot_id, key.user_id)
        entry = self._entries.setdefault(identity, _Entry())
        entry.users += 1
        try:
            async with entry.lock:
                yield
        finally:
            entry.users -= 1
            if not entry.users:
                del self._entries[identity]

    async def close(self) -> None:
        # Active/waiting entries remove themselves even during cancellation.
        pass
