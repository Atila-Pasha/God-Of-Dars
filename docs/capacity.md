# Capacity deployment (4 vCPU / 8 GiB)

Run `docker compose -f compose.yaml -f compose.capacity.yaml up -d --build`.
The overlay starts one main/admin polling process and two attack processes.
Only the polling process sends Telegram notifications. Attack processes claim
PostgreSQL jobs using `SKIP LOCKED` and enqueue durable notifications. Never
scale the polling service above one replica for a token.

The connection budget is 40 for polling/admin/notification work plus 8 for
each of two attack processes: 56 total, leaving headroom within PostgreSQL's
120 connections for maintenance and health checks. PostgreSQL uses 1536 MiB
shared buffers, 5 GiB estimated cache, 4 MiB per sort/hash operation and up to
four parallel workers. There is no CPU affinity cap: the scheduler can use all
four CPUs. Keep RAM headroom; allocating all RAM to pools is counterproductive.

Per-user FSM isolation serializes game updates across chats. Different users
run concurrently. Locks are removed when the last waiter finishes. Membership
checks coalesce simultaneous requests and evict individual cache entries;
reaching capacity no longer empties the entire cache. Long polling bypasses the
outgoing API semaphore. In-flight updates get 40 seconds to drain at shutdown.

SQL statements time out after 30 seconds and row lock waits after 10 seconds.
The notification batch is kept at the sender concurrency so work does not sit
leased in a large in-process queue. Delivery remains at least once: a timeout
after Telegram accepts a message can still produce a duplicate.

Every minute, `capacity` logs report loop lag, connection-pool state, update
counts/errors, and bounded latency samples. Container health checks verify both
an application heartbeat (maximum age 30 seconds) and database connectivity.
Docker marks stale heartbeats unhealthy; it does not automatically restart a
merely unhealthy container. Runtime crashes restart via `unless-stopped`.
Logs rotate at 5 x 20 MiB per container.

## Reproduce load measurements

Use a separate database named `godofdars_capacity_probe`. Run migrations and
`python scripts/seed_capacity.py` once to create 10,000 synthetic users. The
seed command refuses other database names. Never point dispatcher probes at
production: some menu flows initialize game state.

```
python scripts/dispatcher_load_test.py --concurrency 160 --operations 5000 --latency-ms 50
python scripts/dispatcher_load_test.py --concurrency 500 --operations 10000 --latency-ms 200
python scripts/load_test.py --concurrency 160 --operations 5000 --users 1000 --mode resource
```

The dispatcher probe uses real middleware, handlers and PostgreSQL but replaces
Telegram transport. Its scenario names `attack`, `purchase`, `notification`, and
`broadcast` represent menu/read paths, not completed attacks, purchases, or mass
sends. Integration tests separately cover competing writes, rewards, attack
claims and outbox claims. Concurrency in this probe is injected directly into
`feed_update`, so it can deliberately exceed the production polling limit.
Latency excludes waiting for the probe's admission semaphore. These numbers
are not a guarantee of real Telegram delivery throughput or total active users.
Telegram network latency, flood limits, command mix and large history tables
remain external or workload-dependent limits.

## Rollback on the configured server

Pre-deployment code/config archive, database dump, and test evidence are kept
under `/root/godofdars-capacity-backup`. The previous image is tagged
`godofdars:before-capacity`. Stop the two attack containers before rolling back
to the combined runtime. Restore the previous Compose files/environment and
use the saved image for `bot`; do not restore the database dump unless data
recovery is actually required. This release changes no database schema.

Configuration references: [aiogram polling concurrency](https://docs.aiogram.dev/en/latest/dispatcher/dispatcher.html)
and [PostgreSQL resource settings](https://www.postgresql.org/docs/17/runtime-config-resource.html).
