# Testing Strategy

See [[../decisions/0005-test-database-strategy|0005-test-database-strategy]] for the full
rationale.

## Backend

Real Postgres, not SQLite — the schema uses UUID PKs, `TIMESTAMPTZ`, and will grow
enums/JSONB that SQLite either fakes or ignores. `backend/tests/conftest.py`:

- `_apply_migrations` (session-scoped, autouse) runs `alembic upgrade head` against
  `TEST_DATABASE_URL` once per test session — the same migrations that run in production.
- `db_session` (function-scoped) opens a connection, begins an outer transaction, binds an
  `AsyncSession` to it with `join_transaction_mode="create_savepoint"`, and rolls back the
  outer transaction after each test — full isolation without drop/recreate per test. **Engine
  is created per-test, not session-scoped** — pytest-asyncio gives each test its own event
  loop by default, and a shared engine/connection created in one loop breaks when a later test
  runs in a different loop ("attached to a different loop"). If you reach for a
  session-scoped engine fixture again, make sure the event-loop scope actually matches, or
  keep it per-test as it is now.
- `app`/`client` fixtures build the FastAPI app with `get_db_session` overridden to yield the
  transactional `db_session`, so HTTP-level tests (`httpx.AsyncClient` + `ASGITransport`) share
  the same transaction as direct-repository tests and see the same isolation guarantees.

Run: `TEST_DATABASE_URL=postgresql+asyncpg://... uv run pytest` (defaults to
`localhost:5432/nova_test`, matching the Docker Compose Postgres with a second database).

Test types per module (see `backend/tests/modules/tenants/` as the pattern):
`test_domain.py` (pure functions, no DB), `test_repository.py` (isolation/persistence),
`test_router.py` (end-to-end via HTTP).

**Not built yet**: testcontainers-based ephemeral DB for CI isolation — flagged in ADR-0005 as
a future upgrade once CI needs it.

## Frontend

`pnpm run check` (svelte-check, type + Svelte-specific checks) and `pnpm run build` are run in
CI-equivalent form. No component/e2e test framework is set up yet — add one when there's real
UI worth testing beyond the current placeholder pages.
