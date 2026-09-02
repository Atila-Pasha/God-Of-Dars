from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_BOT_TOKEN: str | None = None
    ADMIN_IDS: str = ""
    DATABASE_URL: str
    ENVIRONMENT: str = "development"
    REQUIRED_CHANNELS: str = ""
    TELEGRAM_PROXY: str | None = None

    @property
    def required_channel_list(self) -> tuple[str, ...]:
        return tuple(
            channel.strip()
            for channel in self.REQUIRED_CHANNELS.split(",")
            if channel.strip()
        )

    @property
    def admin_id_set(self) -> frozenset[int]:
        ids: set[int] = set()
        for value in self.ADMIN_IDS.split(","):
            value = value.strip()
            if value:
                try:
                    ids.add(int(value))
                except ValueError as exc:
                    raise ValueError("ADMIN_IDS must contain Telegram numeric IDs") from exc
        return frozenset(ids)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
