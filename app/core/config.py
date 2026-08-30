from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
