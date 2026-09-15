from app.core.config import Settings


def make_settings(database_url: str, **values) -> Settings:
    return Settings(
        BOT_TOKEN="test-token",
        DATABASE_URL=database_url,
        _env_file=None,
        **values,
    )


def test_legacy_postgres_urls_use_asyncpg() -> None:
    for prefix in ("postgres://", "postgresql://"):
        configured = make_settings(f"{prefix}user:pass@db/example")
        assert configured.DATABASE_URL == ("postgresql+asyncpg://user:pass@db/example")


def test_removed_api_environment_keys_are_ignored() -> None:
    configured = make_settings(
        "postgresql+asyncpg://user:pass@db/example",
        API_JWT_SECRET="retired-setting",
    )

    assert not hasattr(configured, "API_JWT_SECRET")
