from pydantic import Field
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
    DAILY_QUEST_TIMEZONE: str = "UTC"
    API_PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"
    API_ALLOWED_ORIGINS: str = ""
    API_ACCESS_TOKEN_MINUTES: int = Field(default=15, ge=1, le=60)
    API_REFRESH_TOKEN_DAYS: int = Field(default=30, ge=1, le=365)
    API_LOGIN_ATTEMPT_MINUTES: int = Field(default=10, ge=2, le=30)
    API_IDEMPOTENCY_HOURS: int = Field(default=24, ge=1, le=168)
    API_CLEANUP_INTERVAL_SECONDS: float = Field(default=3600, ge=60)
    REDIS_URL: str | None = None
    API_OUTBOUND_PROXY: str | None = None
    API_JWT_ISSUER: str = "godofdars-api"
    API_JWT_AUDIENCE: str = "godofdars-flet"
    API_JWT_SECRET: str | None = None
    TELEGRAM_CLIENT_ID: str | None = None
    TELEGRAM_CLIENT_SECRET: str | None = None
    TELEGRAM_REDIRECT_URI: str | None = None
    TELEGRAM_OIDC_ISSUER: str = "https://oauth.telegram.org"
    TELEGRAM_OIDC_AUTH_URL: str = "https://oauth.telegram.org/auth"
    TELEGRAM_OIDC_TOKEN_URL: str = "https://oauth.telegram.org/token"
    TELEGRAM_OIDC_JWKS_URL: str = "https://oauth.telegram.org/.well-known/jwks.json"
    TELEGRAM_OIDC_SCOPES: str = "openid profile telegram:bot_access"

    def validate_api_production(self) -> None:
        if self.ENVIRONMENT.casefold() != "production":
            return
        missing: list[str] = []
        if not self.API_JWT_SECRET or len(self.API_JWT_SECRET.encode()) < 32:
            missing.append("API_JWT_SECRET (at least 32 bytes)")
        if not self.TELEGRAM_CLIENT_ID:
            missing.append("TELEGRAM_CLIENT_ID")
        if not self.TELEGRAM_CLIENT_SECRET:
            missing.append("TELEGRAM_CLIENT_SECRET")
        if not self.API_PUBLIC_BASE_URL.startswith("https://"):
            missing.append("API_PUBLIC_BASE_URL (HTTPS)")
        if not self.telegram_redirect_uri.startswith("https://"):
            missing.append("TELEGRAM_REDIRECT_URI (HTTPS)")
        if missing:
            raise ValueError(
                "API production configuration is invalid: " + ", ".join(missing)
            )

    @property
    def api_allowed_origin_set(self) -> frozenset[str]:
        return frozenset(
            value.strip().rstrip("/")
            for value in self.API_ALLOWED_ORIGINS.split(",")
            if value.strip()
        )

    @property
    def telegram_redirect_uri(self) -> str:
        if self.TELEGRAM_REDIRECT_URI:
            return self.TELEGRAM_REDIRECT_URI
        return f"{self.API_PUBLIC_BASE_URL.rstrip('/')}/api/v1/auth/telegram/callback"

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
    )


# Values are supplied by pydantic-settings from the process environment/.env.
# Static type checkers cannot infer those runtime-provided required fields.
settings = Settings()  # type: ignore[call-arg]
