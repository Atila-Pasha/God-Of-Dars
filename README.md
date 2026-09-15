# GodOfDars

An asynchronous educational strategy game delivered through Telegram. The
runtime contains the main bot, an optional admin bot, PostgreSQL-backed job
workers, and durable notification delivery. There is no HTTP API or public
network port.

## Requirements

- Python 3.12+
- PostgreSQL 15+
- A Telegram bot token
- An optional second token and a numeric allow-list for the admin bot

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
alembic upgrade head
python -m app.main
```

Set `BOT_TOKEN`, `DATABASE_URL`, and production admin values in `.env` before
starting. Required subscription channels are managed through the admin bot.

## Docker deployment

The included Compose stack starts one bot process and PostgreSQL without
exposing a port publicly. Copy the example environment file, replace every
secret, then start the stack:

```bash
cp .env.example .env
docker compose up --build -d
docker compose logs -f bot
```

The container runs `alembic upgrade head` before the bot starts and fails fast
if PostgreSQL is unavailable. It also includes a database-aware health check.
For production, keep PostgreSQL backups and pin the image produced by CI rather
than rebuilding directly on every host.

Telegram long polling must have exactly one active main-bot process for a bot
token. Scale throughput with the concurrency, worker, cache, and database-pool
settings below; do not run multiple polling replicas with the same token.

## Capacity settings

- `BOT_CONCURRENCY_LIMIT`: maximum concurrently handled Telegram updates.
- `TELEGRAM_HTTP_LIMIT`: HTTP connection-pool size for Telegram.
- `TELEGRAM_API_CONCURRENCY`: global Bot API backpressure.
- `DB_POOL_SIZE` / `DB_MAX_OVERFLOW`: database connection limits. Keep their
  sum below PostgreSQL's available connections, including workers and admin.
- `WORKER_COUNT`: parallel attack resolvers.
- `NOTIFICATION_WORKER_COUNT`: parallel durable notification senders.
- `GROUP_USER_CACHE_*`: bounded cache that avoids a user lookup for every group
  message.

Start with the values in `.env.example`, then tune using the test database and
the included probes:

```bash
python scripts/load_test.py --concurrency 100 --operations 5000 --users 1000
python scripts/dispatcher_load_test.py --help
```

Notifications use an at-least-once outbox. A provider timeout after Telegram
accepted a message can therefore produce a duplicate, but notifications are
not silently lost.

## Verification

```bash
ruff check .
ruff format --check .
mypy app admin
pytest
alembic heads
```

The historical API migration remains in the Alembic chain so existing
databases can upgrade safely. The current head then removes its six API-only
tables. Back up any retired API authentication or audit data before deploying;
the downgrade restores empty table structures, not deleted rows.
