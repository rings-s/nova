# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

NOVA is a multi-tenant booking and customer-operations platform for GCC beauty/wellness businesses: salons and spas, with walk-in queues, WhatsApp messaging and deposits. The tree currently holds only the backend.

- **`nova_backend/`**: FastAPI on Python 3.13, SQLAlchemy 2 async + asyncpg, Alembic, and an ARQ worker on Redis. Managed with `uv`.
- **`infra/`**: a docker compose stack that reads `infra/.env`. Services: postgres 16, redis, a one-shot `migrate`, `backend`, `worker`, an on-demand `tools` container, and an optional `cloudflared` profile.
- **`docs/`**: numbered design docs (Obsidian-style `[[links]]`) and ADRs in `docs/decisions/`. Code comments cite them as `docs/10 section 12` or `ADR-0010`.
  - `docs/12-Backend-Code-Walkthrough.md` is the onboarding guide.
  - `nova_backend/README.md` is the maintained code map.

The SvelteKit frontend is not in the tree. CI's frontend jobs skip unless `frontend/package.json` exists.

`base-projects/` is a stray local virtualenv, not project code.

## Commands

The Makefile is at the repo root.

| Command                                     | What it does                                                                                                                                                                                                       |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `make dev`                                  | Starts the full stack via compose. Migrations run first in the `migrate` container. API docs at http://localhost:8000/docs. Creates `infra/.env` from the example if it is missing, generating every blank secret. |
| `make test`                                 | Runs `pytest` in a one-off `tools` container, against the `nova_test` database.                                                                                                                                    |
| `make check`                                | ruff, mypy, and a `create_app()` assembly smoke check. No database needed.                                                                                                                                         |
| `make lint` / `make fmt` / `make typecheck` | `ruff check` / `ruff format` / `mypy app`, on the host via `uv run`.                                                                                                                                               |
| `make revision m="add_x"`                   | `alembic revision --autogenerate` in a one-off `tools` container.                                                                                                                                                  |
| `make migrate`                              | `alembic upgrade head` in a one-off `tools` container.                                                                                                                                                             |

To run a single test:

```bash
# DB-backed tests: in the stack's tools container, the one that holds TEST_DATABASE_URL
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm tools \
  uv run pytest tests/modules/booking/test_availability.py::test_name -q

# Pure tests (tests/test_architecture.py, every test_domain.py) need no DB: run on the host
cd nova_backend && uv run pytest tests/test_architecture.py tests/modules/booking/test_domain.py -q
```

DB-backed tests on the host:

- They read `TEST_DATABASE_URL`, which defaults to `postgresql+asyncpg://nova:nova@localhost:5432/nova_test`. Point it at the `POSTGRES_PORT` and `POSTGRES_PASSWORD` set in `infra/.env`. It names the schema owner: conftest migrates as the owner, then runs every test as `nova_app` with `SET LOCAL ROLE`.
- `infra/postgres/initdb/` creates `nova_test` and the `nova_app` login only when the volume is first initialised. On an existing volume, do both by hand:
  `docker compose -f infra/docker-compose.yml --env-file infra/.env exec postgres createdb -U nova nova_test`
  `make db-app-role`

CI (`.github/workflows/ci.yml`) runs:

- ruff, mypy and pytest
- the assembly smoke check
- `alembic upgrade head` followed by `alembic check` on an empty database. This fails when models changed without a migration.

## Architecture

### Vertical slices with enforced layering

Each bounded context is a package under `app/modules/`: identity, catalog, discovery, booking, queue, payment, billing, analytics, media, notification, ai_agents. Every package has the same files: `router`, `schemas`, `service`, `domain`, `models`, `repository`, `events`, `exceptions`, `dependencies`. `booking` is the reference implementation.

`analytics` (docs/13, ADR-0011) is the exception. It owns no tables, so it has no `models`, `repository` or `events`. It reads fact projections (`BookingFact`, `PaymentFact`, …) through the other modules' services, and adds `metrics.py` (pandas and numpy) and `charts.py` (Plotly JSON).

- **Start with the module's `__init__.py` docstring.** It names the aggregates and the _public surface_ that other modules may import. A test requires the docstring.
- **Dependencies point inward:** `router → service → domain ← repository`. `tests/test_architecture.py` enforces this by AST inspection:
  - `domain.py` may not import fastapi, starlette, sqlalchemy or httpx.
  - `service.py` and `models.py` may not import fastapi or starlette.
  - No module, router included, may import another module's `models` or `repository`.
  - Only `analytics/metrics.py` and `analytics/charts.py` may import numpy, pandas or plotly.
- **Cross-module access goes through the other module's service.**
  - Outside request DI (worker, webhooks, other services), use the `build_*_service(session, tenant_id)` factory in that module's `dependencies.py` rather than wiring repositories by hand.
  - For a reaction rather than a question, publish a domain event instead. Booking never imports notification or billing.
- **`domain.py` comes in two styles.** Use a rich entity only when the thing can be in an invalid state.
  - _Pure validator functions_, where the ORM model is the entity: identity, catalog, discovery, media, notification. `analytics` is pure too, with no ORM model at all.
  - _Rich entities with state machines_, kept separate from the ORM record, with the repository mapping between them (e.g. `domain.Booking` vs `models.BookingRecord`): booking, queue, payment, billing.
- **`app/modules/registry.py` is the single wiring point.**
  - It imports every module's models, which Alembic autogenerate needs.
  - It lists the routers that `main.py` mounts under `/api/v1`.
  - Import order matters for FK resolution.
- **Services `flush()` and never commit; routers commit.** That way one endpoint can compose several service calls atomically.
  - The AI chat route is the exception. Inference takes seconds, so a turn holds no request transaction: `ai_agents/dependencies.py::TenantServiceScope` opens, scopes and commits one short unit of work per tool call. A tool's write is committed when the tool returns, and the fallback model is not retried after one.
- **Errors:**
  - Domain and service code raise `DomainError` subclasses (`app/core/exceptions.py`, each carrying `status_code` and `code`), never `HTTPException`.
  - `core/error_handlers.py` renders every error as the `{"error": {code, message, field, retryable}}` envelope, including `IntegrityError` and uncaught exceptions.
  - `app/db/errors.py` maps constraint names to domain errors, e.g. `ex_bookings_no_provider_overlap` → 409 `slot_unavailable`. The names come from the naming convention in `app/db/base.py`.

### Multi-tenancy: three layers, keep all of them

1. **Authorization.** `tenant_id` comes only from the URL path (`/tenants/{tenant_id}/...`), never from the body or query. `core/deps.py::get_tenant_context` authorizes the principal (through `get_authorized_tenant`), then calls `set_tenant_scope`. The AI chat, which holds no request transaction, depends on `get_authorized_tenant` alone; `tests/test_route_guards.py` lists it.
2. **Application.** Tenant-owned models use `TenantOwnedMixin`. Their repositories extend `TenantScopedRepository`, which filters every query and rejects writes for another tenant.
3. **Database.** Postgres RLS with `FORCE`. `app.current_tenant_id` is set per transaction with `SET LOCAL`, and an unscoped connection sees zero rows.
   - **Autogenerate does not emit RLS.** A migration that creates a tenant-owned table must enable and force RLS and create the `tenant_isolation` policy itself. Copy the `_TENANT_TABLES` loop in `alembic/versions/e5f6a7b8c9d0_*.py`.

There are two sanctioned exceptions:

- **`bypass_tenant_scope`**: for the worker, the outbox and maintenance jobs — and, narrowly, for the two request paths whose entire job is to answer "which tenant" before any tenant is known or authorized: `AuthService._issue_pair` reading `memberships` at login, and `MembershipService.accept_invite` validating an invite token before trusting the tenant it names (`SELF_AUTHORIZING_TENANT_ROUTES` in `tests/test_route_guards.py`). Both close the bypass (via `set_tenant_scope`) before any other read or write. Do not add a third without the same justification.
- **`set_discovery_scope`**: for the public marketplace (`discovery`, ADR-0010). It is SELECT-only and sees only published listings, through catalog's `PublicCatalogService`.

**Never connect the app as a role RLS exempts.** Postgres skips every policy for a superuser or a `BYPASSRLS` role, `FORCE` or not.

- The API and worker connect as `nova_app` (NOSUPERUSER NOBYPASSRLS, created and granted DML by migration `e1f2a3b4c5d6`). Only migrations and the test suite use the schema owner, through `MIGRATION_DATABASE_URL` and `TEST_DATABASE_URL`, and compose gives those to the `migrate` and `tools` containers alone.
- `enforce_rls_role` (`app/db/session.py`) refuses to start a staging or production process that is connected as an exempt role.
- `set_tenant_scope` also switches off any earlier `bypass_tenant_scope` in the same transaction.
- Tests run as `nova_app` too. Fixtures seed rows as the owner through `as_owner`. Repository isolation tests read as the owner, so that only the repository's own filter can pass them.
- `tests/test_row_level_security.py` fails when a tenant table lacks a forced `tenant_isolation` policy, or when `nova_app` lacks DML on a table.

Caller identity is never read from the request. `customer_id` is derived from the principal. Only staff and service principals may pass `on_behalf_of_customer_id` (see `resolve_booking_customer`).

A self-service booking or queue join resolves the caller's own customer record through `CustomerService.ensure_for_user`, which may _claim_ an existing, unclaimed record by phone match — but only once `User.phone_verified_at` is set (`AuthService.request_phone_verification` / `confirm_phone_verification`, a short-lived JWT sent over WhatsApp, signed with a purpose-derived key via `security.purpose_key`/`issue_purpose_token`/`decode_purpose_token` rather than a stored, hashed one-time code — nothing backs the token but its own signature). An unverified phone that matches any existing record, claimed or not, is refused (`PhoneVerificationRequiredError`) rather than told which case it is.

Staff access is granted through a redeemable invite (`MembershipService.invite` / `accept_invite`), never by matching an email string against whoever already holds a NOVA account with it. The token returned at invite time is the entire credential — NOVA does not deliver it; the inviter relays it out of band.

### Auth, rate limits, idempotency

- **Tokens.** `app/core/security.py` verifies HS256 bearer JWTs (stdlib only) into a `Principal` of kind STAFF, CUSTOMER or SERVICE.
  - Every request re-reads a staff or customer token's account (`token_version`, `is_active`) through `get_token_state_lookup`, in a session of its own. Bumping `token_version` (logout-everywhere, `MembershipService.revoke`) ends every token at once. Tests that run the real token path override that dependency (`tests/modules/identity/test_token_revocation.py`).
  - `kind=service` skips that account re-check — it names no account — so it is the one claim a leaked `SECRET_KEY` turns into permanent, unrevocable access (docs/14 TM-03). The app itself never puts it on a bearer token; a request bearing one is refused outside `local`/`test`. Every token's `exp - iat` is also capped at the refresh-token TTL, so a forged token cannot claim an unbounded lifetime either.
  - A customer may reach any tenant, because it is a marketplace. So operational routes need `Depends(require_staff)`, and customer reads need per-row ownership checks (see `BookingService.get_for_principal`).
  - Routes that move money or read what a business earns need a role permission instead: `Depends(RequirePermission(StaffPermission.X))` from `identity/dependencies.py`. The role is read from this tenant's `memberships` row, never from `Principal.roles`, which is flattened across tenants. The policy is one table in `identity/domain.py`. `tests/test_route_guards.py` lists which routes need which permission.
  - With `AUTH_DEV_BYPASS=true`, a request without an `Authorization` header becomes a SERVICE principal. `Settings` refuses to load with the flag set unless `ENV` is `local` or `test`, and whenever `CLOUDFLARE_TUNNEL_TOKEN` is set (`config.py::dev_bypass_refusal`).
- **Rate limits.** Write endpoints declare `dependencies=[Depends(write_rate_limit)]` from `core/throttling.py`.
  - IP buckets come from `client_ip_key`. That is the TCP peer, or the header `Settings.trusted_client_ip_header` names: `CLIENT_IP_HEADER`, else `CF-Connecting-IP` while a tunnel token is set. Never `X-Forwarded-For`, whose first entry the client writes.
  - **Login** (`auth_service.py`):
    - It allows 5 failures per account per client address in 15 minutes.
    - It locks an account after 20 consecutive failures from anywhere; each lock restarts the count.
    - Every refusal, a locked account included, answers `invalid_credentials`.
    - The router commits on `InvalidCredentialsError`, or the count rolls back with the error.
- **Payments.**
  - Only staff may set a payment intent's `amount` or `currency` (`payment/dependencies.py::refuse_customer_amount`).
  - `return_url` must be on `PUBLIC_APP_URL`'s origin.
  - The webhook captures only when the reported amount and currency match the payment row. Otherwise it records the event, answers `amount_mismatch`, and leaves the payment uncaptured.
- **Idempotency.** Retryable create-style POSTs take `idempotency_guard("<op>")` from `core/idempotency.py` (see `queue/router.py::join_queue`). A key is scoped to its endpoint, tenant and principal.
  1. Run every authorization check first. A replay skips the handler, so a check after `guard.begin` never runs for it.
  2. Call `guard.begin(...)`. If it returns a replay, return that.
  3. Call `guard.complete(...)` before committing.

### Domain events and the worker

- **Publishing.** `core/events.py::publish_event(session, event)` inserts into the `domain_events` outbox inside the caller's transaction. Events are frozen dataclasses subclassing `DomainEvent`, and the event name is the class name.
- **Dispatch.** The ARQ worker (`app/worker/arq_worker.py`) dispatches the outbox every 10s.
  - `worker/outbox.py` runs the handlers registered with `@subscribe("EventName")` in `app/worker/handlers.py`.
  - Add reactions there, not in the module that raises the event.
- **Delivery is at-least-once.** Handlers must be idempotent: use dedupe keys or check state first.
- **The worker is load-bearing.** Without it, no notification is sent and no commission accrues.
- **Cross-tenant cron jobs follow one pattern:**
  1. Read the candidates with `bypass_tenant_scope`.
  2. Process each tenant in its own session with `set_tenant_scope`.
  3. Commit per tenant, and catch exceptions per tenant.

### Persistence and configuration conventions

- **Mixins** live in `app/db/mixins.py`.
  - `TimestampMixin` sets `__mapper_args__ = {"eager_defaults": True}`. A model that declares its own `__mapper_args__` must keep that key, or endpoints returning an updated row raise `MissingGreenlet`.
  - `SoftDeleteMixin` is **not** auto-filtered.
- **Bilingual text** is stored as `name_en`/`name_ar` column pairs, both required (`core/validators.py::require_bilingual_text`, ADR-0004).
- **Money** uses `core/values.Money`. The defaults are SAR and Asia/Riyadh.
- **Migrations.** `alembic/env.py` takes the database URL from `Settings.migration_database_url`, falling back to `Settings.database_url`, never from `alembic.ini`. Always read an autogenerated migration before keeping it.
- **Settings** (`app/core/config.py`, `lru_cache`d) requires `DATABASE_URL`, `REDIS_URL` and `SECRET_KEY`. `ENV` defaults to `production`. An empty `SECRET_KEY` is refused everywhere, and outside `local`/`test` so is one under 32 characters or starting with "change". Integration credentials (Moyasar, Nextcloud, WhatsApp) are optional: without them the adapters raise `IntegrationNotConfiguredError`, a 503 `integration_not_configured`, and the app still boots. `/docs`, `/redoc` and `/openapi.json` are served only when `ENV` is local or test, unless `API_DOCS_ENABLED` says otherwise.
- **AI is optional.**
  - PydanticAI and Ollama are reached only through `ai_agents/runtime.py`, via a guarded import (`uv sync --extra ai`; `make image EXTRAS=ai` for the production image). Without them, agents degrade to a human handoff.
  - The roster is data in `ai_agents/agents.py` (docs/13, ADR-0011). Owner agents (accountant, analyst, business manager) are staff-only, need a role permission (`required_permission`), are bound to one business, and may state only numbers a tool returned. The business manager proposes actions and never applies them.
  - A turn holds no transaction (see "Services `flush()`" above). What a write tool produced for the client comes back in `AiChatResponse.held_slots` and `queue_places`, even with a handoff. The model never sees a hold token.
  - No agent cancels. `request_cancellation` checks the booking against `BookingService.preview_cancellation` and returns it in `pending_cancellations`; the customer confirms through the booking's cancel route.
  - **Conversation memory** is in Redis (`ai_agents/history.py`). Recent turns are keyed by tenant, principal, business and a hash of `session_id`, with a TTL and a turn cap. An unreachable Redis gives a fresh turn, never a failed one. Tool results from earlier turns still count as grounded.
  - `tests/modules/ai_agents/` asserts that every other flow works offline. `test_turns.py` runs whole turns against PydanticAI's `FunctionModel`, and conftest gives each test app an in-memory conversation store.
  - Agents call services, never repositories.

### Tests

- **Real Postgres, never SQLite** (ADR-0005).
  - `tests/conftest.py` applies the Alembic migrations once per session, and only for tests that request `db_session`.
  - Each test runs inside an outer transaction (with savepoints) that is rolled back afterwards.
  - Keep every `test_domain.py` DB-free.
- **Fixtures.** `client` overrides `get_db_session` and `get_principal`. The default principal is SERVICE; override the `principal` fixture to test authorization.
- **Factories:** `tenant_factory`, `business_factory`, `location_factory`, `service_factory`, `provider_factory`, `customer_factory`, and `qualify` (assigns a provider to a service).
- **New modules** get `tests/modules/<name>/` with `test_domain.py` (no DB), `test_repository.py` (tenant isolation) and `test_router.py`.

## Gotchas

- **ADRs can be stale.** Their "Consequences" sections describe the code at the time the ADR was written. ADR-0006, for example, lists RLS, the outbox, rate limiting and idempotency as missing, and all of them exist now. Trust the code.
- **SELinux.** Any bind mount added to `infra/docker-compose.yml` needs the `:z` label, like the existing ones.
- **Compose hardening, keep all of it.**
  - Published ports bind to `127.0.0.1`.
  - Redis requires `REDIS_PASSWORD`.
  - `backend` and `worker` get no schema-owner credentials: compose blanks `POSTGRES_PASSWORD` in them.
  - ARQ jobs are JSON, not pickle (`WorkerSettings.job_serializer`). With pickle, anyone who can write to Redis runs code in the worker.
  - `infra/.env.example` holds no secret values, and `make infra/.env` generates them. The repository is public.
- **Dev image.**
  - The venv lives at `/opt/venv` so the `/app` bind mount cannot shadow it.
  - The container UID must match the host's (`UID`/`GID` in `infra/.env`), because `alembic revision` writes into the mount.
