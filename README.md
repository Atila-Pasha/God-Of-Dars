# GodOfDars

An asynchronous educational strategy game delivered through Telegram. The
runtime contains the main bot, an optional admin bot, PostgreSQL-backed job
workers, and durable notification delivery. There is no HTTP API or public
network port.

The private server-backup integration uses Dropbox only to create and rotate
encrypted database backup files. See the [Privacy Policy](PRIVACY.md) for
details.

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
- `NOTIFICATION_SEND_CONCURRENCY`: concurrent notification sends per worker;
  keep this at or below `TELEGRAM_API_CONCURRENCY` unless the global Telegram
  limiter is intentionally serving as the final queue.
- `TTT_TIMEOUT_BATCH_SIZE` / `TTT_TIMEOUT_CONCURRENCY`: expired games processed
  per sweep and in parallel; keep concurrency below the available DB pool.
- `GROUP_USER_CACHE_*`: bounded cache that avoids a user lookup for every group
  message.

Start with the values in `.env.example`, then tune using the test database and
the included probes:

```bash
python scripts/load_test.py --concurrency 100 --operations 5000 --users 1000
python scripts/dispatcher_load_test.py --help
```

## Leaderboard widget preview

Telegram's [widget-sandbox](https://github.com/TelegramMessenger/widget-sandbox)
uses the production Bot API 10.4 `sendWidget` method. To test the HTML cards locally:

```bash
python -m scripts.preview_leaderboard_widget
```

Open `http://127.0.0.1:8765/` for sample commander, student, and global-rank
cards. To send real widgets, run `python -m app.main` with a production bot
token. Older Telegram clients may show only the widget caption. If Telegram
rejects a widget, the bot falls back to its existing leaderboard text.
Production widgets currently work only in private chats with the bot. Telegram
automatically protects these messages, so users cannot forward the widgets;
`protect_content=false` does not override this server-side restriction.

Leaderboard rows, pagination counts, and user positions are cached per bot
process for one hour (`LEADERBOARD_CACHE_TTL_SECONDS=3600`). Cards show the
snapshot's last update time in Tehran. The global rank widget embeds a compact
sprite made from the rank tiers' Telegram custom emoji thumbnails.

## Tic-tac-toe

Use `/game` in the bot's private chat. The menu offers classic tic-tac-toe and
advanced tic-tac-toe (five in a row on a 10×10 board), each against the
computer or a real opponent. Human matches can be friendly or wagered in coins
(gold) or diamonds. Enter an opponent's `@username` or numeric Telegram ID;
they must have started the bot before they can receive an invitation.
The advanced game displays the entire 10×10 board in a Telegram widget. Tap an
empty square directly to place a piece. Older 15×15 matches remain playable.

When a wagered invitation is accepted, both stakes move out of spendable
balances into the match. The winner receives both stakes; a draw refunds both.
Each turn has 60 seconds, measured on the server, and an expired turn loses.
Invitations expire after five minutes. Match and escrow state are stored in
PostgreSQL so restarts do not reset the deadline or stake.

Advanced tic-tac-toe requires a Telegram client that supports message widgets.
Its HTML board is the only play interface;
if sending it fails, the match is cancelled and any reserved stakes are refunded.
Classic tic-tac-toe still uses inline buttons when a widget is unavailable.
The widget feature is available in the production Bot API 10.4.

## Car game

The `/game` menu also offers a three-lane car game in a private Telegram widget.
Tap Start, then use the left and right buttons to dodge obstacles and collect
coins and diamonds. Road events and lane changes are scored on the server; the
pace increases during a run. At a collision, the collected rewards are added to
the player's balance in one transaction. Rewards are capped by actual play time
at 50 coins and 10 diamonds per minute. A new run starts from `/game` after a
crash. This game requires Bot API 10.4 and a compatible Telegram client.

## Chess

The `/game` menu also offers chess in a Telegram message widget. The challenger
plays white; the opponent or computer plays black. Tap a piece and then its
destination. Pawn promotion offers queen, rook, bishop, and knight. The server
validates all moves, including check, castling, en passant, and draws. As with
tic-tac-toe, invitations expire after five minutes and each turn has 60 seconds.
Human matches can be friendly or wagered in coins or diamonds; stakes are held
when the invitation is accepted and settled at the end of the match.

To try chess locally with `@godofdarstestbot`, set a local PostgreSQL
`DATABASE_URL` and the test bot's `BOT_TOKEN` in `.env`, then run:

```bash
python -m alembic upgrade head
python -m scripts.run_local_game_test
```

The test runner refuses non-local databases and tokens for other bots. Open
`@godofdarstestbot` in Telegram, send `/game`, and choose Chess. The production
server remains on the current version until this local flow is approved.

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

For the 4-vCPU / 8-GiB production deployment, worker separation, monitoring,
load-test interpretation and rollback, see [the capacity runbook](docs/capacity.md).
