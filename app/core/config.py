from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_BOT_TOKEN: str | None = None
    ADMIN_IDS: str = ""
    DATABASE_URL: str
    ENVIRONMENT: str = "development"
    TELEGRAM_PROXY: str | None = None
    DB_POOL_SIZE: int = Field(default=20, ge=1)
    DB_MAX_OVERFLOW: int = Field(default=30, ge=0)
    DB_POOL_TIMEOUT: int = Field(default=30, gt=0)
    DB_POOL_RECYCLE: int = Field(default=1800, gt=0)
    BOT_CONCURRENCY_LIMIT: int = Field(default=100, ge=1)
    ADMIN_CONCURRENCY_LIMIT: int = Field(default=10, ge=1)
    TELEGRAM_HTTP_LIMIT: int = Field(default=100, ge=1)
    BROADCAST_BATCH_SIZE: int = Field(default=100, ge=1)
    TELEGRAM_SEND_DELAY: float = Field(default=0.04, ge=0)
    MEMBERSHIP_CACHE_TTL: float = Field(default=60, ge=0)
    MEMBERSHIP_CACHE_MAX_ENTRIES: int = Field(default=10_000, ge=100)
    CHANNELS_CACHE_TTL: float = Field(default=30, ge=0)
    GROUP_REGISTER_CACHE_TTL: float = Field(default=300, ge=0)

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
