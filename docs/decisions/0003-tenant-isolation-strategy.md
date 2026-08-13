# 0003 — Tenant Isolation Strategy

## Context

NOVA is multi-tenant: each business (tenant) can have multiple branches, and later,
bookings/queues/payments per branch. A cross-tenant data leak (tenant A reading/writing tenant
B's data) would be a severe defect.

## Decision

Enforce isolation at the **application/repository layer** via `TenantScopedRepository`
(`backend/app/db/repository.py`): every query method it exposes filters by `tenant_id`, and
there is no unscoped method on that base class to reach for by mistake. `tenant_id` is resolved
once from the URL path (`get_tenant_context`) and fixed at repository construction time — never
taken from a request body or query parameter.

Not implementing Postgres Row-Level Security (RLS) yet.

## Consequences

- Cross-tenant leakage is prevented for anything going through the repository layer —
  verified by `backend/tests/modules/tenants/test_repository.py`.
- Simple: no `SET LOCAL app.tenant_id` session-state management, works cleanly with normal
  connection pooling.
- **Known gap**: does not protect raw SQL or a future module that bypasses
  `TenantScopedRepository`. This is an application-layer control, not a database-layer one.

## Alternatives considered

Postgres Row-Level Security — the natural defense-in-depth layer, deferred as future hardening.
**To verify**: whether compliance/audit requirements (especially once payment or
health-adjacent data exists) mandate RLS before launch.
