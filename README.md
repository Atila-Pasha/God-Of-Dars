UNDER ACTIVE DEVELOPMENT

## HTTP API for Flet

GodOfDars includes a versioned FastAPI backend for Windows, Android, and Linux
clients. It reuses the bot's domain services and PostgreSQL data, while running
as a separate process:

```bash
alembic upgrade head
python -m app.api
```

Copy the API and Telegram OIDC settings from `.env.example` into your private
`.env`. Never place the Telegram client secret or `API_JWT_SECRET` in the Flet
application. Development OpenAPI documentation is served at `/docs`; see
[`app/api/README.md`](app/api/README.md) for the login flow and deployment
requirements.

# Operational semantics

Telegram notifications use a durable, idempotent outbox with bounded retries
and stale-job recovery. Delivery is intentionally **at least once**: Telegram
does not provide a provider-side idempotency key, so a process crash after
`send_message` succeeds but before the database records `SENT` can result in a
duplicate external message. Game-state transactions and economic rewards are
not duplicated by this delivery window.

## PostgreSQL capacity probe

The read-only capacity probe uses the real async SQLAlchemy session and
`UserRepository` against the configured PostgreSQL database. It never calls the
Telegram API:

```bash
python scripts/load_test.py --concurrency 50 --operations 500
python scripts/load_test.py --mode resource --concurrency 50 --operations 500
```

`read` measures repository reads. `resource` exercises a real row-locked
resource mutation and rolls it back after the database work, so it does not
alter game state. These numbers describe backend database capacity on the test
host; they are not Telegram delivery capacity.
