# 0006 — API Security, Reliability, and Observability Baseline

## Status

Accepted — 2026-08-15

## Context

A backend-architecture review of the `identity`, `catalog`, and `booking` slices found seven
defects. Two were severe enough to block any deployment:

1. **No authentication existed anywhere.** Every endpoint was reachable by anyone who could
   reach the host. `tenant_id` was read from the URL path and used directly to scope
   repositories, with nothing verifying the caller was entitled to that tenant. ADR-0003 secured
   the plumbing — `TenantScopedRepository` genuinely prevents leaking across tenants — but the
   front door was open, so the isolation it provided was decorative. `GET /tenants/{id}/...`
   with any valid UUID returned that tenant's data.

2. **Identity was client-supplied.** `customer_id` was an ordinary field on
   `CreateBookingRequest` and a query parameter on the booking list endpoint. Any caller could
   create bookings in another person's name and read anyone's booking history.

And five more:

3. `IntegrityError` was unhandled, so every database constraint surfaced as a 500 — including
   the `EXCLUDE` constraint that is the _actual_ guarantee against double-booking. The one
   defence that works under concurrency reported itself as a server fault.
4. No catch-all exception handler. Unexpected errors reached Starlette's default, returning an
   unstructured 500 and exposing tracebacks whenever `DEBUG` was on.
5. The error envelope was `{"code", "message"}`, but docs/07 and `core.schemas.ErrorResponse`
   both declare `{"error": {...}}`. Any client written against the documentation would break.
6. No correlation ids, and `logging.basicConfig` with a plain format string meant every
   `logger.info(..., extra={...})` call silently discarded its structured fields.
7. No connection-pool sizing and no statement timeout; a single runaway query could hold a
   pooled connection indefinitely.

## Decision

### Authentication and authorization — `app/core/security.py`

A `Principal` (subject, kind, tenant memberships, roles) is resolved from an HS256 bearer token
verified against `settings.secret_key`. Implemented on the standard library rather than adding a
dependency, and deliberately **verify-only** — NOVA does not mint production tokens here.

- Signature comparison is constant-time.
- The algorithm is pinned to HS256; the token's own `alg` header is never trusted (this is how
  "alg: none" forgeries work).
- An `exp` claim is mandatory.
- It **fails closed**: a missing or invalid token is 401 in every environment.
- `AUTH_DEV_BYPASS` exists for local development and **raises** if enabled while `ENV` is not
  `local` or `test`, so it cannot silently disable authentication in a deployed environment.

`get_tenant_context` now delegates to `require_tenant_access`, which returns 403 when the
principal is not a member of the path's tenant. `tenant_id` still comes only from the path, so a
request cannot widen its own scope.

### Caller identity is never taken from the request

`customer_id` is removed from the booking request body and derived from the principal.
`resolve_booking_customer` permits an explicit `on_behalf_of_customer_id` for staff and service
principals only; a customer supplying it gets 403. The same rule governs the list endpoint.

### Constraint violations become correct status codes — `app/db/errors.py`

A translation layer maps SQLSTATE and constraint names to domain errors:
`ex_bookings_no_provider_overlap` → 409 `slot_unavailable`, unique → 409, foreign key → 422
`invalid_reference`, check → 422. A constraint firing under concurrency is an expected outcome,
not a fault, and 409 responses are marked `retryable`.

### One error contract — `app/core/error_handlers.py`

Handlers for `DomainError`, `IntegrityError`, `RequestValidationError`, `HTTPException`, and a
final catch-all for `Exception`. All produce the documented `{"error": {...}}` envelope with a
`correlation_id`. The catch-all logs the traceback and returns a stable code — internal details
never cross the boundary. Domain errors log at INFO (expected business outcomes); unexpected
errors log at ERROR, keeping alerting signal clean.

### Observability — `app/core/context.py`, `middleware.py`, `logging.py`

A `ContextVar`-based request context carries correlation id, tenant, and principal. Middleware
assigns a correlation id per request, honours an inbound `X-Correlation-ID` so upstream traces
continue, echoes it on the response, and emits access logs with duration and status. Logging is
JSON in deployed environments and human-readable locally, with `extra` fields and request
context attached to every record.

### Operational hardening

Pool sizing, `pool_recycle`, `pool_timeout`, a server-side `statement_timeout`, and
`application_name` for attribution in `pg_stat_activity`. `/health` (liveness, touches nothing)
is split from `/health/ready` (readiness, checks the database) so a brief database blip stops
traffic being routed rather than triggering a restart loop. Startup refuses a `*` CORS origin
while credentials are enabled.

### API contract

List endpoints return the declared `Page[T]` envelope instead of a bare array, so `total` and
`next_cursor` can be added without a breaking change.

## Consequences

- **Breaking, deliberately**: all endpoints now require `Authorization: Bearer <token>`; the
  error envelope is nested; list responses are wrapped in `{"items": [...]}`; `customer_id` is
  gone from the booking request body; `/health/db` is now `/health/ready`.
- Authentication is verify-only. **A token issuer, a user/membership store, and refresh/rotation
  do not exist yet** — `Principal.tenant_ids` is trusted from the token, so whatever mints tokens
  becomes security-critical. That is the next piece of work.
- No rate limiting yet, so brute-forcing a token is unthrottled. Cloudflare in front is the
  interim control.
- No idempotency keys on POST endpoints; a retried booking creation can produce a duplicate
  where the slot allows it.
- Domain events are still published before commit, so an event can describe a transaction that
  rolled back. The transactional outbox in docs/08 §16 remains outstanding.
- Postgres RLS is still not enabled — tenant isolation remains an application-layer control
  (ADR-0003's known gap), now with an authorization layer above it.

## Alternatives considered

**PyJWT / python-jose** — rejected for now: verification is ~40 lines of stdlib, and avoiding the
dependency keeps the local-first deployment lean. Revisit when RS256 or JWKS rotation is needed,
which a real issuer will likely require.

**Enforcing auth via middleware instead of dependencies** — rejected: middleware cannot see which
route matched, so it cannot distinguish public endpoints (health) from tenant-scoped ones without
duplicating the routing table. Dependencies put the requirement next to the endpoint.

**Returning 404 instead of 403 for another tenant's resource** — considered, since 403 confirms a
tenant id exists. Rejected because tenant ids are not secrets and 403 is far more debuggable.
Revisit if enumeration becomes a concern.
