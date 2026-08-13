# Multi-Tenancy

Narrative version of [[0003-tenant-isolation-strategy|../decisions/0003-tenant-isolation-strategy]]
— read that ADR for the full justification and alternatives considered.

## The guarantee

A request scoped to tenant A can never read or write tenant B's rows, for any tenant-owned
entity (branches today; bookings, queues, etc. later).

## How it's enforced today

`TenantScopedRepository` (in `backend/app/db/repository.py`) bakes a `tenant_id` filter into
every query method — there is no unscoped method to reach for by mistake. `tenant_id` is
resolved once, from the URL path (`get_tenant_context` in `app/core/deps.py`), and passed into
the repository at construction time — never from a request body or query parameter, so a
request can't influence its own tenant scope.

This is an **application-layer** control. It protects everything that goes through the
repository layer. It does not protect raw SQL or a future module that bypasses
`TenantScopedRepository`.

## Future hardening

Postgres Row-Level Security (`SET LOCAL app.tenant_id`) is the natural defense-in-depth layer
once compliance or audit requirements demand it — not built yet. **To verify**: whether
handling payment or health-adjacent data will require RLS before launch.
