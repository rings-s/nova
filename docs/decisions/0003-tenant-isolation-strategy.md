# 0003 — Tenant Isolation Strategy

## Status

Superseded in part — 2026-08-16. The decision below to defer Postgres Row-Level Security no
longer holds: RLS shipped in migration `d4e5f6a7b8c9`, and migration `e5f6a7b8c9d0` extends the
same policy to every table added since. `TenantScopedRepository` remains, but it is no longer
the only thing standing between two salons' data. Read the "Known gap" below as closed.

## Context

NOVA is multi-tenant: each business (tenant) can have multiple branches, and later,
bookings/queues/payments per branch. A cross-tenant data leak (tenant A reading/writing tenant
B's data) would be a severe defect.

## Decision

Enforce isolation at the **application/repository layer** via `TenantScopedRepository`
(`nova_backend/app/db/repository.py`): every query method it exposes filters by `tenant_id`, and
there is no unscoped method on that base class to reach for by mistake. `tenant_id` is resolved
once from the URL path (`get_tenant_context`) and fixed at repository construction time — never
taken from a request body or query parameter.

~~Not implementing Postgres Row-Level Security (RLS) yet.~~ **Superseded**: RLS is now enabled
and `FORCE`d on every tenant-owned table. Each request sets `app.current_tenant_id` on its
connection via `SET LOCAL` (`app/db/session.py`), and every policy compares `tenant_id` against
it, so a connection that never sets it sees nothing. The dispatcher and webhook paths that
legitimately cross tenants set `app.bypass_rls` explicitly.

## Consequences

- Cross-tenant leakage is prevented for anything going through the repository layer —
  verified by `nova_backend/tests/modules/catalog/test_repository.py`.
- Simple: no `SET LOCAL app.tenant_id` session-state management, works cleanly with normal
  connection pooling.
- ~~**Known gap**: does not protect raw SQL or a future module that bypasses
  `TenantScopedRepository`. This is an application-layer control, not a database-layer one.~~
  **Closed** by the RLS policies above. Note that a Postgres _superuser_ bypasses RLS entirely
  regardless of `FORCE`, so the application must not connect as one. **Update 2026-09-14:** it
  did, in the compose stack and in the test suite, until migration `e1f2a3b4c5d6`, so the
  policies were in force nowhere. The API, the worker and the tests now connect as `nova_app`
  (NOSUPERUSER NOBYPASSRLS), and `tests/test_row_level_security.py` checks the policies as it.

## Alternatives considered

Postgres Row-Level Security — was deferred as future hardening; now implemented, so this is no
longer an alternative but the current state. See ADR-0007 for the contexts added under it.
