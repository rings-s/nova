# 0005 — Test Database Strategy

## Context

The schema uses UUID primary keys, `TIMESTAMPTZ`, and will grow enums/JSONB. Tests need to be
fast and isolated, but also representative of the real database.

## Decision

Real Postgres, not SQLite — a second logical database (`nova_test`) alongside the main one.
`backend/tests/conftest.py`:

- Migrations applied once per test session (`alembic upgrade head` against
  `TEST_DATABASE_URL`), so tests exercise the same migrations that run in production.
- Each test gets its own outer transaction + `create_savepoint` join mode, rolled back after
  the test — full isolation without dropping/recreating schema per test.
- The engine/connection are created **per test function**, not shared across the session — an
  earlier session-scoped engine caused "attached to a different loop" failures because
  pytest-asyncio gives each test its own event loop by default while `asyncio_mode = "auto"`'s
  fixture loop scope didn't match. Documented in [[../operations/testing-strategy]] so this
  isn't rediscovered the hard way again.

## Consequences

- Tests catch real Postgres-specific behavior (constraint names, `TIMESTAMPTZ` semantics) that
  SQLite would silently fake or ignore.
- Requires a running Postgres reachable at `TEST_DATABASE_URL` — one more moving part than an
  in-memory SQLite DB, acceptable given the Compose stack already provides Postgres.

## Alternatives considered

**SQLite (in-memory or file)** — rejected: would pass tests against behavior Postgres doesn't
actually have, defeating the point of testing against "the same DB as production."

**testcontainers-python** for a fully ephemeral, parallel-safe database per test run — not
adopted yet. Worth it once CI needs isolation from a shared dev Postgres, or wants a clean
container per pipeline run. **To verify**: whether the CI environment supports
docker-in-docker for testcontainers.
