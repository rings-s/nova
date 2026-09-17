# 0007 — Completing the Remaining Bounded Contexts

## Status

Accepted — 2026-08-16

## Context

Five of the eight bounded contexts named in `docs/02` were directory stubs: `queue`,
`payment`, `media`, `notification`, and `ai_agents`. `booking` was implemented but missing the
half that makes it usable — there was no schedule to generate availability from, no
availability endpoint, and no reschedule. Several cross-cutting pieces existed as code nobody
called: `core/idempotency.py` had zero call sites, `WRITE_POLICY` was defined and never
applied, and `core/events.py` wrote to an outbox that no dispatcher ever read.

Three defects blocked correctness rather than features:

1. **`POST /tenants`, `GET /tenants` and `GET /tenants/{id}` were unauthenticated.** ADR-0006
   states that all endpoints require a bearer token; these were the exception. Anyone who could
   reach the host could create tenants and enumerate every business on the platform along with
   its phone number.
2. **CI had not run since the `backend/` → `nova_backend/` rename.** Every backend job set
   `working-directory: backend`, so lint, type checking, migrations and tests had all been
   silently skipped. `mypy` was invoked by a job but was not a declared dependency, and three
   jobs lacked the environment variables `Settings` requires.
3. **`alembic check` failed on pre-existing model/migration drift.** The naming convention in
   `app/db/base.py` renders `ck_%(table_name)s_%(constraint_name)s`, so a model-side constraint
   already named `ck_bookings_end_after_start` became `ck_bookings_ck_bookings_end_after_start`.
   The functional index `uq_users_email_lower` existed only in the migration.

## Decision

### Customers live in `identity`

`docs/06` lists `Customer` as a core aggregate but never places it in a context. It goes in
`identity`, which already owns the User/customer distinction. A customer is _who someone is_;
catalog answers _what is sold_ and booking _when_.

Customers are tenant-scoped, with `phone` unique per tenant. The same person at two salons is
two customer records with two consent states — consent given to one business must never leak to
another. `user_id` links a record to a sign-in account when someone books themselves, and is
null for a walk-in reception typed in.

`resolve_booking_customer` still returns an id whose meaning depends on the branch taken (the
caller's own _user_ id, or a _customer_ id staff named); `CustomerService.resolve_for_booking`
is the single place that ambiguity is resolved into a record. Conflating them is how a user id
ends up in a `customer_id` column.

### Availability is generated, never stored

`generate_availability` is a pure function over working windows, dated exceptions, and taken
intervals. Determinism (docs/09 #4) follows from purity: same inputs, same slots, same order.
Slots are generated on a grid anchored to each window's own start, so changing opening hours
does not silently shift every slot.

Working hours are stored as local wall-clock minutes from midnight, interpreted in the
location's timezone. Storing UTC would be wrong — "we open at 9am" survives a DST change, a
stored offset does not. Dates are walked in local time, because a UTC day boundary falls at
03:00 in Riyadh.

Every returned slot carries an HMAC `slot_id` over (tenant, provider, service, start). That is
what enforces docs/07 §5's "AI agents may query availability but must not invent slots".

### Slot holds are in Postgres, not Redis

`docs/08` §1 lists temporary slot holds under Redis. They are a Postgres table instead, for the
same reason `idempotency_keys` already is: a hold that evaporates on a Redis restart sells the
same slot twice, and the hold must be checked in the same transaction as the insert that
consumes it.

### Walk-ins and appointments share one ordered timeline

`queue.domain.priority_key` maps every entry onto a single instant: an appointment sorts at its
booked time, a walk-in at its arrival time plus a penalty. A 17:00 booking therefore does not
jump the queue at 09:00, and a walk-in standing at the desk does not beat the customer who
booked ahead. Ordering is derived, never stored — `position` is a monotonic join counter used
for audit and tie-breaking, and there is deliberately no endpoint to reorder the line by hand.

### Tickets carry a hash, and the payload carries no PII

A QR payload is `<ticket_id>.<token>.<signature>` and nothing else. Only a SHA-256 hash of the
token is stored, so reading the tickets table does not let anyone check in as somebody else.
Every validation failure raises one generic error, so a scanner cannot be used as an oracle.
Redemption is idempotent — a scanner double-firing at a busy reception desk must not produce an
error.

### Payment state stays separate from booking state

The webhook endpoint is the only unauthenticated write path in the system, so its order is
fixed: verify the signature against the **raw** body, record the raw payload, stop if the
`(provider, external_event_id)` index says it is a duplicate, resolve the tenant, re-scope the
connection for RLS, then apply. It answers 200 for events it does not act on, because a non-2xx
makes the gateway retry something that will never succeed.

Capture is idempotent, and only advances a booking that is actually waiting — a cancelled
booking whose payment lands late must not spring back to life. Refunds are separate rows;
status is derived from the arithmetic so a caller cannot mark a payment fully refunded while
returning half the money.

### The binary never passes through FastAPI

`media` issues a scoped, short-lived, signed authorisation to write to one exact path; the
browser PUTs to Nextcloud directly. There is deliberately no endpoint accepting a file body.
`assert_path_belongs_to_tenant` runs on every read and write.

### Notification is a consumer, and consent is a gate

Three gates before any message leaves: consent (per channel, and separately for marketing),
quiet hours (marketing only, evaluated in the _customer's_ timezone), and a dedupe key. Refused
messages are recorded as `SUPPRESSED`, deliberately not `FAILED` — nothing went wrong, and the
record is the evidence the opt-out was honoured.

### AI guardrails are code, and PydanticAI is optional

`docs/10` §11 requires guardrails to be code rather than prompt text, and they are: tenant
scoping at `AgentDeps` construction, an allowlist that simply never registers an unlisted tool,
PII redaction and injection framing pre-prompt, Pydantic output validation, and a router rate
limit. `confirm_booking` appears in no allowlist, so no agent has a tool that could reach it.

PydanticAI is an optional extra (`uv sync --extra ai`) rather than a hard dependency, because
docs/10 §12 requires every flow to remain usable with the inference engine offline. The runtime
degrades to a static reply with `requires_human_handoff=True` when the library is absent, the
model is unreachable, or a turn times out.

### The outbox is delivered at-least-once

`app/worker/outbox.py` claims batches with `FOR UPDATE SKIP LOCKED` plus a lease, and processes
each event in its own transaction so one poisonous event cannot roll back its batch. Events are
marked published _after_ their handlers run, which is at-least-once and requires handlers to be
idempotent — the alternative drops notifications whenever a worker dies mid-handler.

## Consequences

- **Breaking**: `POST /tenants` now requires authentication and makes the caller the owner;
  `GET /tenants` returns only the caller's own tenants rather than every tenant on the platform.
- `bookings` gained a `notes` column; `customers` is now a real table and `booking.customer_id`
  refers to it rather than to a user id.
- A domain-raised 409 is now marked `retryable`, matching the constraint-raised one. The same
  condition had different retry semantics depending on which layer caught the race.
- Model-side check constraints are named _bare_ (`end_after_start`, not
  `ck_bookings_end_after_start`); the naming convention adds the prefix. Adding one the old way
  will fail `alembic check`.
- The worker is now load-bearing. Without a running `arq` process, domain events accumulate
  undelivered and no customer is notified of anything.
- Deployments that want AI must `uv sync --extra ai` and run Ollama. Nothing else changes.
- `retention_agent`, `insights_agent` and `billing_agent` from docs/10 §3 remain unimplemented:
  they need the `analytics` and `billing` module surfaces, which do not exist. They are declared
  unavailable rather than given stub data to invent numbers from.

## Alternatives considered

**Slot holds in Redis, as docs/08 §1 specifies** — rejected above. Worth revisiting if hold
volume ever makes the write load on Postgres matter, which at salon scale it will not.

**A transparent idempotency middleware** instead of the explicit `IdempotencyGuard` — rejected:
middleware cannot see which route matched, and an endpoint that silently does nothing because a
key was replayed is very hard to debug. The route reads `begin` / `complete` explicitly.

**Letting reception call any customer out of order** — rejected. `call_next` asks the domain who
is next. An endpoint that let staff pick would make "deterministic ordering" untrue on the first
busy Thursday.

**Making PydanticAI a hard dependency** — rejected: it contradicts docs/10 §12, and a local-first
deployment that never enables AI should not carry the inference stack.
