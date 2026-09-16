from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    BOT_USERNAME: str | None = None
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
    TELEGRAM_API_CONCURRENCY: int = Field(default=30, ge=1)
    TELEGRAM_RETRY_AFTER_MAX: int = Field(default=3, ge=0)
    WORKER_COUNT: int = Field(default=4, ge=1)
    NOTIFICATION_WORKER_COUNT: int = Field(default=4, ge=1)
    NOTIFICATION_SEND_CONCURRENCY: int = Field(default=20, ge=1)
    WORKER_POLL_INTERVAL: float = Field(default=2.0, gt=0)
    WORKER_BATCH_SIZE: int = Field(default=100, ge=1)
    ATTACK_MAX_RETRIES: int = Field(default=3, ge=0)
    ATTACK_RETRY_BASE_SECONDS: float = Field(default=5.0, gt=0)
    ATTACK_PROCESSING_TIMEOUT_SECONDS: float = Field(default=120.0, gt=0)
    NOTIFICATION_MAX_RETRIES: int = Field(default=5, ge=0)
    NOTIFICATION_RETRY_BASE_SECONDS: float = Field(default=5.0, gt=0)
    NOTIFICATION_PROCESSING_TIMEOUT_SECONDS: float = Field(default=120.0, gt=0)
    BROADCAST_BATCH_SIZE: int = Field(default=100, ge=1)
    TELEGRAM_SEND_DELAY: float = Field(default=0.04, ge=0)
    MEMBERSHIP_CACHE_TTL: float = Field(default=60, ge=0)
    MEMBERSHIP_CACHE_MAX_ENTRIES: int = Field(default=10_000, ge=100)
    CHANNELS_CACHE_TTL: float = Field(default=30, ge=0)
    GROUP_REGISTER_CACHE_TTL: float = Field(default=300, ge=0)
    GROUP_REGISTER_CACHE_MAX_ENTRIES: int = Field(default=10_000, ge=100)
    GROUP_USER_CACHE_TTL: float = Field(default=60, ge=0)
    GROUP_USER_CACHE_MAX_ENTRIES: int = Field(default=50_000, ge=100)
    DAILY_QUEST_TIMEZONE: str = "UTC"
    LEADERBOARD_TIMEZONE: str = "Asia/Tehran"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        """Make common PostgreSQL URLs use the required async driver."""
        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            return "postgresql+asyncpg://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            return "postgresql+asyncpg://" + value.removeprefix("postgresql://")
        return value

    @property
    def admin_id_set(self) -> frozenset[int]:
        ids: set[int] = set()
        for value in self.ADMIN_IDS.split(","):
            value = value.strip()
            if value:
                try:
                    ids.add(int(value))
                except ValueError as exc:
                    raise ValueError(
                        "ADMIN_IDS must contain Telegram numeric IDs"
                    ) from exc
        return frozenset(ids)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        # Removed API variables may still exist in an older production .env.
        # Ignoring unknown keys keeps that upgrade non-breaking.
        extra="ignore",
    )


# Values are supplied by pydantic-settings from the process environment/.env.
# Static type checkers cannot infer those runtime-provided required fields.
settings = Settings()  # type: ignore[call-arg]
