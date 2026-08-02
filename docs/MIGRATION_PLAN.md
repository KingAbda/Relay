# Controlled-trial database migration runbook

Last updated: 2026-08-02

Status: **SQLite and disposable PostgreSQL 16 forward/rollback proven; persistent migration remains prohibited without production-like readiness and recovery evidence**.

Relay uses Flask-Migrate 4.1.0 and Alembic 1.18.5. Application startup never
creates or upgrades persistent tables. The migration history contains:

- `20260713_00`: the frozen schema represented by the committed pre-readiness models.
- `20260713_01`: the controlled-trial adoption revision.
- `20260731_01`: the additive authentication-event audit trail and current model head.

The independent legacy fixture in `tests/legacy_schema.py` is not imported by a
migration. Tests seed users, accounts, signed ledger entries, sessions, a series,
listings, requests, wants, a review, waitlist data, and a password-reset record.

## Safety properties

Before changing a business table, the adoption revision fails on fractional or
negative balances, fractional/zero ledger entries, account/ledger mismatches,
non-trial prices, self-sessions, invalid/duplicate reviews, unknown transaction
types, and dangling related-user references. It never rounds, repairs, or deletes
those rows. Legacy ledger events receive deterministic `legacy:<transaction-id>`
idempotency keys and retain their IDs, amounts, descriptions, related users, and
timestamps. Legacy verification secrets are invalidated. Reset secrets are changed
to SHA-256 while the raw submitted token remains usable after upgrade.

Downgrade is intentionally fail-closed when authentication audit events exist.
Downgrade to the legacy revision is also fail-closed when new moderation,
consent, email, dispute, block, role/account-state, disputed-session, or controlled-
trial ledger data exists. That data cannot be represented safely by the old app.
An immediate compatibility rollback preserves users, balances, session rows, and
ledger rows; reset-token rows remain but their one-way hashes cannot become the
original raw secrets, so password resets must be reissued after rollback.

## Fresh disposable database

```text
DATABASE_URL=sqlite:////tmp/relay-fresh-rehearsal.sqlite \
  .venv/bin/flask --app app.main db upgrade
DATABASE_URL=sqlite:////tmp/relay-fresh-rehearsal.sqlite \
  .venv/bin/flask --app app.main db current
DATABASE_URL=sqlite:////tmp/relay-fresh-rehearsal.sqlite \
  .venv/bin/flask --app app.main db check
```

## Existing pre-Alembic Relay database

Do not apply these commands to an unknown database. First identify the owner,
matching application revision, tested backup, and isolated restore. Compare its
schema and aggregate counts with `tests/legacy_schema.py`; resolve every preflight
exception through a reviewed, attributable decision rather than editing balances.

```text
# Stamp only after proving the database is the frozen legacy shape.
DATABASE_URL=postgresql+psycopg://... \
  .venv/bin/flask --app app.main db stamp 20260713_00
DATABASE_URL=postgresql+psycopg://... \
  .venv/bin/flask --app app.main db upgrade 20260731_01
DATABASE_URL=postgresql+psycopg://... \
  .venv/bin/flask --app app.main db current
DATABASE_URL=postgresql+psycopg://... \
  .venv/bin/flask --app app.main db check
```

For an immediate rollback before the new application writes unrepresentable data:

```text
DATABASE_URL=postgresql+psycopg://... \
  .venv/bin/flask --app app.main db downgrade 20260713_00
```

If downgrade preflight refuses, keep the service unavailable and restore the last
jointly verified application/database backup or roll forward. Never force the old
schema by dropping new audit data.

## Verified local evidence

```text
.venv/bin/python -m unittest tests.test_migrations -v
# 4 tests passed: fresh head/no drift, representative legacy upgrade+rollback,
# unsafe-upgrade rejection, and rollback refusal with no partial change.

RELAY_TEST_POSTGRES_URL=postgresql+psycopg://relay:relay-ci-only@127.0.0.1:55432/relay_migration_ci \
RELAY_POSTGRES_TEST_DESTRUCTIVE_OK=true \
  .venv/bin/python -W error::DeprecationWarning -m unittest \
    tests.postgres_migrations tests.postgres_concurrency -v
# Ran 5 tests — OK: fresh head/no drift, representative legacy
# upgrade+rollback, competing holds, competing completion confirmations,
# and cancellation racing a completion confirmation.
```

The PostgreSQL transcript was reproduced on 2026-07-13 with the official
`postgres:16` Docker image (server 16.14) in container
`relay-postgres-migration-ci`, bound only to `127.0.0.1:55432`. The guarded URL
named only `relay_migration_ci`; no existing or remote database was connected.
Both explicit suites now destroy their disposable schema after execution.

A separately guarded production-shaped test migrated an empty disposable database
to exact head, checked for drift, connected to disposable Redis 7.4.9 database 15,
and received `200` from `/health/ready`. It then destroyed the PostgreSQL schema
and flushed Redis. The CI workflow provisions the same PostgreSQL and Redis major
versions and repeats those checks.

This proves the prepared migration, competing-write, local shared-limiter, and
production-shaped readiness harnesses. It does not prove real SMTP delivery,
provider-native backup/restore, the deployed proxy/NAT topology, or a persistent
database migration. Those checks remain required before any persistent database
is migrated.

The exact disposable container commands are:

```text
docker run --name relay-postgres-migration-ci --rm -d \
  -e POSTGRES_USER=relay -e POSTGRES_PASSWORD=relay-ci-only \
  -e POSTGRES_DB=relay_migration_ci \
  -p 127.0.0.1:55432:5432 postgres:16
docker run --name relay-redis-ci --rm -d \
  -p 127.0.0.1:56379:6379 redis:7.4-alpine

RELAY_TEST_POSTGRES_URL=postgresql+psycopg://relay:relay-ci-only@127.0.0.1:55432/relay_migration_ci \
RELAY_POSTGRES_TEST_DESTRUCTIVE_OK=true \
  .venv/bin/python -W error::DeprecationWarning -m unittest \
    tests.postgres_migrations tests.postgres_concurrency -v

RELAY_TEST_REDIS_URL=redis://127.0.0.1:56379/15 \
RELAY_REDIS_TEST_DESTRUCTIVE_OK=true \
  .venv/bin/python -W error::DeprecationWarning -m unittest tests.redis_proxy -v

RELAY_TEST_POSTGRES_URL=postgresql+psycopg://relay:relay-ci-only@127.0.0.1:55432/relay_migration_ci \
RELAY_POSTGRES_TEST_DESTRUCTIVE_OK=true \
RELAY_TEST_REDIS_URL=redis://127.0.0.1:56379/15 \
RELAY_REDIS_TEST_DESTRUCTIVE_OK=true \
  .venv/bin/python -W error::DeprecationWarning -m unittest \
    tests.production_infrastructure -v

docker stop relay-redis-ci relay-postgres-migration-ci
```
