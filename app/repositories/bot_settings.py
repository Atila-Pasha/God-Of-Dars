from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot_settings import BotSettings
from app.models.required_channel import RequiredChannel


class BotSettingsRepository:
    """Persistent bot-wide settings edited from the admin panel."""

    async def get(self, session: AsyncSession) -> BotSettings:
        result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = BotSettings(id=1, is_active=True)
            session.add(settings)
            await session.flush()
        return settings

    async def set_channel(
        self, session: AsyncSession, *, telegram_id: int | None, username: str | None
    ) -> BotSettings:
        settings = await self.get(session)
        settings.required_channel_telegram_id = telegram_id
        settings.required_channel_username = username.strip().lstrip("@") if username else None
        settings.is_active = bool(telegram_id or username)
        await session.flush()
        return settings

    async def clear_channel(self, session: AsyncSession) -> BotSettings:
        return await self.set_channel(session, telegram_id=None, username=None)

    async def list_channels(self, session: AsyncSession) -> list[RequiredChannel]:
        result = await session.execute(
            select(RequiredChannel).where(RequiredChannel.is_active.is_(True)).order_by(RequiredChannel.id)
        )
        return list(result.scalars().all())

    async def add_channel(self, session: AsyncSession, value: str) -> RequiredChannel:
        value = value.strip()
        telegram_id = int(value) if value.lstrip("-").isdigit() else None
        username = None if telegram_id is not None else value.lstrip("@").strip()
        if not username and telegram_id is None:
            raise ValueError("channel identifier is empty")
        channel = RequiredChannel(telegram_id=telegram_id, username=username, is_active=True)
        session.add(channel)
        await session.flush()
        return channel

    async def remove_channel(self, session: AsyncSession, channel_id: int) -> bool:
        result = await session.execute(select(RequiredChannel).where(RequiredChannel.id == channel_id))
        channel = result.scalar_one_or_none()
        if channel is None:
            return False
        await session.delete(channel)
        await session.flush()
        return True
