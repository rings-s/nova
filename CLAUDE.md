# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

NOVA is a multi-tenant booking and customer-operations platform for GCC beauty/wellness businesses: salons and spas, with walk-in queues, WhatsApp messaging and deposits.

- **`nova_backend/`**: FastAPI on Python 3.13, SQLAlchemy 2 async + asyncpg, Alembic, and an ARQ worker on Redis. Managed with `uv`.
- **`nova-frontend/`**: SvelteKit 2 + Svelte 5 (runes forced for all project files), JavaScript with JSDoc types (no TypeScript sources), Tailwind 4, `adapter-node`, pnpm. See "Frontend" below.
- **`infra/`**: a docker compose stack that reads `infra/.env`. Services: postgres 16, redis, a one-shot `migrate`, `backend`, `worker`, `frontend` (Vite dev on http://localhost:5173), an on-demand `tools` container, and an optional `cloudflared` profile.
- **`docs/`**: numbered design docs (Obsidian-style `[[links]]`) and ADRs in `docs/decisions/`. Code comments cite them as `docs/10 section 12` or `ADR-0010`.
  - `docs/12-Backend-Code-Walkthrough.md` is the onboarding guide.
  - Each numbered doc declares `status: current | design | reference` (legend in `docs/00-Index.md`); `design` docs are the original plan, and the code wins where they disagree. `tests/test_doc_references.py` fails when a doc names a file that doesn't exist or a doc lacks a status; a deliberate miss goes in its `EXPECTED_MISSING` with a reason.
  - Every route's docstring is its `/docs` description; `tests/test_api_docs.py` fails on a route without one.
  - `nova_backend/README.md` is the maintained code map.

CI's frontend jobs are gated on `frontend/package.json`, but the app lives in `nova-frontend/`, so those jobs currently never run. Nothing in CI checks the frontend.

The repo-root `package.json` is a thin npm-workspaces wrapper that delegates to `nova-frontend`. Dependencies belong in `nova-frontend/package.json`.

`base-projects/` is a stray local virtualenv, not project code.

## Commands

The Makefile is at the repo root.

| Command                                     | What it does                                                                                                                                                                                                              |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `make dev`                                  | Starts the full stack via compose. Migrations run first in the `migrate` container. API docs at http://localhost:8000/docs; frontend at http://localhost:5173. Creates `infra/.env` from `infra/.env.example` if missing. |
| `make test`                                 | Runs `pytest` in a one-off `tools` container, against the `nova_test` database.                                                                                                                                           |
| `make check`                                | ruff, mypy, and a `create_app()` assembly smoke check. No database needed.                                                                                                                                                |
| `make lint` / `make fmt` / `make typecheck` | `ruff check` / `ruff format` / `mypy app`, on the host via `uv run`.                                                                                                                                                      |
| `make revision m="add_x"`                   | `alembic revision --autogenerate` in a one-off `tools` container.                                                                                                                                                         |
| `make migrate`                              | `alembic upgrade head` in a one-off `tools` container.                                                                                                                                                                    |
| `make migrate-check`                        | `alembic check` in the `tools` container: fails when models changed without a migration (CI runs the same on an empty database).                                                                                         |
| `make host-env`                             | Writes a git-ignored `nova_backend/.env` (the `nova_app` role, Redis password, `SECRET_KEY`) so `uv run` tools work on the host. Never the schema owner.                                                                 |
| `make ai-eval`                              | Opt-in evaluation of the real model (`tests/ai_eval`, `AI_EVAL=1`). Needs the model server from `AI_BASE_URL`.                                                                                                            |
| `make worker`                               | Runs the ARQ worker inside the `backend` container.                                                                                                                                                                       |

DB-backed tests need only `postgres` and `redis` running, not the whole stack: `docker compose -f infra/docker-compose.yml --env-file infra/.env up -d postgres redis`.

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

Frontend, from `nova-frontend/` (`pnpm-workspace.yaml` must keep `allowBuilds: esbuild: true`; a placeholder value there makes every `pnpm run` fail its pre-run check):

```bash
pnpm run check        # svelte-kit sync + svelte-check over the JSDoc
pnpm run lint         # prettier --check . && eslint .
pnpm run i18n:check   # fails on any t('…') string without an Arabic entry
pnpm run i18n:audit   # lists English still hard-coded in markup
```

- **e2e tests** are Playwright specs named `*.e2e.js` next to the routes they test. `pnpm exec playwright test` runs them all against the dev server on `localhost:5173` (no `webServer`; results go to the OS temp dir). All 96 passed on 2026-09-23.
  - Keep any scratch file, a one-off config included, **outside** `nova-frontend/`. Vite watches the directory, and creating or deleting a file there full-reloads every open page, including pages in the middle of a test.
- **Frontend dependencies.** Add one with `docker compose … exec frontend pnpm add <pkg>` (the bind mount updates `package.json` and the lockfile), or after pulling a change run `… exec frontend pnpm install --frozen-lockfile`; then `restart frontend`. The container's `node_modules` is a named volume that a rebuild never refreshes.
- Open the dev app at `localhost:5173`, not `127.0.0.1`: backend CORS allows only the former.

CI (`.github/workflows/ci.yml`) runs:

- ruff, mypy and pytest
- the assembly smoke check
- `alembic upgrade head` followed by `alembic check` on an empty database. This fails when models changed without a migration.

## Architecture

### Vertical slices with enforced layering

Each bounded context is a package under `app/modules/`: identity, catalog, discovery, booking, queue, review, payment, billing, analytics, notification, ai_agents, call_center, support, admin. (`media` and Nextcloud were removed, ADR-0013; a stale `modules/media/__pycache__` may linger locally.) Every package has the same files: `router`, `schemas`, `service`, `domain`, `models`, `repository`, `events`, `exceptions`, `dependencies`. `booking` is the reference implementation.

`analytics` (docs/13, ADR-0011) is the exception. It owns no tables, so it has no `models`, `repository` or `events`. It reads fact projections (`BookingFact`, `PaymentFact`, …) through the other modules' services, and adds `metrics.py` (pandas and numpy) and `charts.py` (Plotly JSON).

- **Start with the module's `__init__.py` docstring.** It names the aggregates and the _public surface_ that other modules may import. A test requires the docstring.
- **Dependencies point inward:** `router → service → domain ← repository`. `tests/test_architecture.py` enforces this by AST inspection:
  - `domain.py` may not import fastapi, starlette, sqlalchemy or httpx.
  - `service.py` and `models.py` may not import fastapi or starlette.
  - No module, router included, may import another module's `models` or `repository`.
  - Nothing under `app/worker` may import any module's `models` or `repository`.
  - Only `analytics/metrics.py` and `analytics/charts.py` may import numpy, pandas or plotly.
- **Cross-module access goes through the other module's service.**
  - Outside request DI (worker, webhooks, other services), use the `build_*_service(session, tenant_id)` factory in that module's `dependencies.py` rather than wiring repositories by hand.
  - For a reaction rather than a question, publish a domain event instead. Booking never imports notification or billing.
- **`domain.py` comes in two styles.** Use a rich entity only when the thing can be in an invalid state.
  - _Pure validator functions_, where the ORM model is the entity: identity, catalog, discovery, review, notification. `analytics` is pure too, with no ORM model at all.
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
  - A new error code must be added to `docs/15-API-Error-Codes.md` (with its HTTP status) and, for the web app, to `nova-frontend/src/lib/i18n/ar/errors.js`. `tests/test_error_catalog.py` fails until the doc matches; the `tools` container mounts `docs/` read-only at `/docs` for it.

### Multi-tenancy: three layers, keep all of them

1. **Authorization.** `tenant_id` comes only from the URL path (`/tenants/{tenant_id}/...`), never from the body or query. `core/deps.py::get_tenant_context` authorizes the principal (through `get_authorized_tenant`), then calls `set_tenant_scope`. The AI chat, which holds no request transaction, depends on `get_authorized_tenant` alone; `tests/test_route_guards.py` lists it.
2. **Application.** Tenant-owned models use `TenantOwnedMixin`. Their repositories extend `TenantScopedRepository`, which filters every query and rejects writes for another tenant.
3. **Database.** Postgres RLS with `FORCE`. `app.current_tenant_id` is set per transaction with `SET LOCAL`, and an unscoped connection sees zero rows.
   - **Autogenerate does not emit RLS.** A migration that creates a tenant-owned table must enable and force RLS and create the `tenant_isolation` policy itself. Copy the `_TENANT_TABLES` loop in `alembic/versions/e5f6a7b8c9d0_*.py`.

There are three sanctioned exceptions:

- **`bypass_tenant_scope`**: for the worker, the outbox and maintenance jobs — and, narrowly, for the two request paths whose entire job is to answer "which tenant" before any tenant is known or authorized: `AuthService._issue_pair` reading `memberships` at login, and `MembershipService.accept_invite` validating an invite token before trusting the tenant it names (`SELF_AUTHORIZING_TENANT_ROUTES` in `tests/test_route_guards.py`). Both close the bypass (via `set_tenant_scope`) before any other read or write.
- **The superuser console** (`admin`, `/admin/tables/*`): `admin/dependencies.py::get_admin_session` opens `bypass_tenant_scope` after `require_superuser` and leaves it open, because reading every tenant is the point. It reads through `Base.metadata`. It writes two ways, each re-scoped to the row's tenant first (`set_tenant_scope`, which also closes the bypass; a platform table with no `tenant_id` stays bypassed): the curated actions in `admin/domain.py::ACTIONS`, run through the owning module's service, and direct edits (`POST`/`PATCH`/`DELETE …/rows`) that add, change or delete any row of any table except `admin_audit_log`, as plain Core SQL, so no domain rule, event or notification runs, only the database's constraints. A direct edit cannot change a primary key or `tenant_id`, send back a masked value, or delete, deactivate or un-superuser the caller's own account. Credentials are masked (`domain.display_value`) and can be replaced but never read. Every list, view, action and edit goes in `admin_audit_log` (edits with masked before/after values), where `nova_app` lacks UPDATE and DELETE. `tests/test_route_guards.py` keeps the bypass on `/admin/tables`. Do not add a fourth request path without the same justification.
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
  - A staff account is staff only where it has a membership. At any other tenant `get_principal` turns it into a CUSTOMER for the request (`principal_at_tenant`, ADR-0016), and the marketplace assistant takes `get_customer_principal`.
  - Routes that move money, read what a business earns, or change the catalog (services, prices, locations, providers, marketplace listing: `manage_catalog`, owner and manager) need a role permission instead: `Depends(RequirePermission(StaffPermission.X))` from `identity/dependencies.py`. The role is read from this tenant's `memberships` row, never from `Principal.roles`, which is flattened across tenants. The policy is one table in `identity/domain.py`. `tests/test_route_guards.py` lists which routes need which permission.
  - **Superuser** (`users.is_superuser`) is a NOVA administrator, not a salon role. It opens the platform console at `/admin` (every table, read-only and audited; see the `bypass_tenant_scope` exception above) and edits what every tenant shares: today, the service categories (`service_categories`, edited at `/admin/catalog/categories`, read at `GET /discovery/categories`; a service picks one by `category_id`, and salons cannot add their own). Routes depend on `require_superuser` (`identity/dependencies.py`), which re-reads the account row on every request. There is no API to grant it; use `make superuser email=…` (`revoke=1` removes it). The web app asks `GET /auth/me` once per account (`stores/superuser.svelte.js`) whether to show the `/admin` links in the site header and the dashboard sidebar.
  - The dashboard learns the caller's role and permissions for one business from `GET /tenants/{id}/memberships/me` (`accessStore` in the frontend), only to hide what they can't use; every route still checks for itself.
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
  - Checkout is a Moyasar **invoice**, which fixes the amount server-side, paid in Moyasar's embedded Payment Form (`moyasar-payment-form`, `Moyasar.init({invoice_id, …})`, `components/payment/MoyasarForm.svelte`) from the intent's `checkout`; with no `MOYASAR_PUBLISHABLE_KEY`, on the invoice's hosted page (`redirect_url`). The CSP allows `https://api.moyasar.com` for it. `payments.gateway_invoice_id` links it, `gateway_payment_id` is learnt when paid. The payer's return calls `POST …/payments/{id}/sync`; both it and the webhook capture only after fetching Moyasar's own record.
  - The webhook authenticates by the `secret_token` in its body (no signature header) and captures only when the reported amount, currency and invoice match the payment row. Otherwise it records the event, answers `amount_mismatch` or `checkout_mismatch`, and leaves the payment uncaptured.
  - Setup (keys, webhook URL, test cards) is in `nova_backend/README.md` "Payments".
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
- **Each handler runs in its own savepoint** (`worker/outbox.py`). A failing handler rolls back only its own work, the others' commits, and the whole event is retried, so the handlers that succeeded run again.
- **The worker is load-bearing.** Without it, no notification is sent and no commission accrues.
- **Cross-tenant cron jobs follow one pattern:**
  1. Read the candidates with `bypass_tenant_scope`, through the owning module's sweeper (`build_billing_sweeper`, `build_ticket_sweeper`, `build_settlement_reader`, …, in its `dependencies.py`).
  2. Process each tenant in its own session with `set_tenant_scope`.
  3. Commit per tenant, and catch exceptions per tenant.

### Persistence and configuration conventions

- **Mixins** live in `app/db/mixins.py`.
  - `TimestampMixin` sets `__mapper_args__ = {"eager_defaults": True}`. A model that declares its own `__mapper_args__` must keep that key, or endpoints returning an updated row raise `MissingGreenlet`.
  - `SoftDeleteMixin` is **not** auto-filtered.
- **Enum columns** use `app/db/types.py::EnumValue` (a `StrEnum` stored as its *value* in a VARCHAR, never `sqlalchemy.Enum`, which stores member names). Raw SQL and constraints can then say `status = 'confirmed'`. It still reads a legacy member name. A new enum column needs no migration check constraint.
- **Bilingual text** is stored as `name_en`/`name_ar` column pairs, both required (`core/validators.py::require_bilingual_text`, ADR-0004).
- **Money** uses `core/values.Money`. The defaults are SAR and Asia/Riyadh.
- **Plans and trials** (`billing/domain.py`, docs/11 section 2). No plan is free: Solo 400, Studio 600, Chain 1,200 per branch a month, each 10× that a year. Every plan starts with a 7-day trial (10 AI messages for the owner's staff agents: `BillingService.require_ai` checks before the turn, `use_ai_message` counts only a turn a model answered; customer agents and Sara's calls never spend it, or any customer could use it up). A trial that ends unpaid, or a business with no plan, is *locked* (`Subscription.locked_on`): the `expire_trials` cron hides the listing, `BookingService.create` refuses self-service bookings at a `hidden_by_billing` business, the AI answers 402, and the `/app` layout sends staff to Billing (it reads `GET …/subscriptions/{id}/standing`). Other staff routes are locked in the UI only.
- **Business photos** (ADR-0013) belong to `catalog`. Uploads go to the API as the raw request body; `integrations/images.py` re-encodes them to WebP, and they are stored through the `ImageStore` protocol (`integrations/storage`, `LocalImageStore` under `MEDIA_ROOT`). Only `business_photos` rows live in Postgres. They are served by `GET /discovery/photos/{id}/{variant}`: publicly for a listed business, or through an HMAC-signed, expiring link for the owner's preview.
- **Migrations.** `alembic/env.py` takes the database URL from `Settings.migration_database_url`, falling back to `Settings.database_url`, never from `alembic.ini`. Always read an autogenerated migration before keeping it.
- **Settings** (`app/core/config.py`, `lru_cache`d) requires `DATABASE_URL`, `REDIS_URL` and `SECRET_KEY`. `ENV` defaults to `production`. An empty `SECRET_KEY` is refused everywhere, and outside `local`/`test` so is one under 32 characters or starting with "change". Integration credentials (Moyasar, WhatsApp) are optional: without them the adapters raise `IntegrationNotConfiguredError`, a 503 `integration_not_configured`, and the app still boots. `/docs`, `/redoc` and `/openapi.json` are served only when `ENV` is local or test, unless `API_DOCS_ENABLED` says otherwise.
- **AI is optional.**
  - PydanticAI and the model server are reached only through `ai_agents/runtime.py`, via a guarded import (`uv sync --extra ai`; `make image EXTRAS=ai` for the production image). Without them, agents degrade to a human handoff.
  - **The models come from vLLM, in every environment** (ADR-0019, which replaced llama.cpp, ADR-0018, on 2026-10-28): `AI_PROVIDER=vllm`, the compose `llm` service (started by `make dev`, no profile; `http://llm:8000/v1`, the `Settings` defaults). The base file runs vLLM's CPU build (`vllm-cpu-release-repo:v0.10.2`, needs AVX-512); `infra/docker-compose.gpu.yml` swaps in `vllm/vllm-openai:v0.10.2`. Thinking is off two ways: the template's `enable_thinking: false` per request (`runtime.py::_model_settings`, needs `qwen3` in the alias) and `/no_think`; `--reasoning-parser qwen3` keeps any thinking in `reasoning_content`, and `--tool-call-parser hermes` parses tool calls.
  - **vLLM is the only model server.** llama.cpp, Ollama, LM Studio and the hosted `openai_compatible` provider are gone: `AI_PROVIDER` and `VOICE_AI_PROVIDER` accept only `vllm`, so a stale value stops `Settings` from loading. The default model is Qwen3-4B (`LLM_MODEL=Qwen/Qwen3-4B`, served as `qwen3-4b`), for a GPU. vLLM loads full-precision weights (about 8 GB for the 4B), so this CPU-only laptop serves Qwen3-1.7B: `infra/.env` sets `LLM_MODEL`, `LLM_ALIAS` and both `AI_*_MODEL` to it, with `AI_REQUEST_TIMEOUT_SECONDS=1800`. `AI_THINKING=false` (default) adds Qwen3's `/no_think` switch; the generic `thinking=False` (`reasoning_effort`) setting did not finish a turn within 10 min in testing. Keep `LLM_PARALLEL=1` (`--max-num-seqs`) unless `AI_MAX_CONCURRENT_TURNS` rises with it. Setup: `nova_backend/README.md`, "AI agents (local models)".
  - **The reply is in the app's language** (`ar` or `en`, the `locale` the web app sends from its current translation), never the message's. Request schemas normalise it (`guardrails.app_locale`: `ar-SA` → `ar`, anything else → `en`); `_LANGUAGE_RULES` ends the instructions; and `runtime.py`'s `in_app_language` output validator checks the reply and suggested actions by script (`guardrails.in_wrong_language`), sends a wrong one back once, and a second miss fails the turn to the localized fallback. Calls are exempt: Sara answers an English-speaking caller in English.
  - Frontend: `/app/ai` (staff owner agents, filtered by `required_permission`), and `AssistantLauncher` on storefronts (receptionist) and on `/discover` (the marketplace agent, `POST /discovery/ai/chat`, customers only, no tenant). They hide themselves when inference is unavailable.
  - **Agents book in two turns (ADR-0015).** A hold tool offers a slot. `book_held_slot` books only an offer from an _earlier_ turn, kept server-side with its hold token (`history.py` offers), and only the one the customer pressed "Yes, book it" on (the request's `confirm_hold_token`); a yes typed in words is refused with `not_confirmed`. It goes through `BookingService.create` (a `draft`; staff or a payment confirms it) and issues the QR ticket, returned in `AiChatResponse.tickets`. The model never sees hold tokens or QR payloads.
  - Marketplace tools name listings by slug; the server resolves the tenant and opens that tenant's `TenantServiceScope` (`AgentToolkit._tenant_scope`). The tenant chat route refuses `marketplace_agent`, and vice versa (`AgentSpec.marketplace`).
  - Tickets: a booking's ticket lasts until the appointment ends plus `TICKET_TTL_HOURS`. Reissuing revokes the old QR, so the frontend keeps tickets per device (`stores/tickets.js`). Staff scan at `/app/check-in` (camera via `jsqr`, or a pasted code or handheld scanner); check-in needs a confirmed booking.
  - The roster is data in `ai_agents/agents.py` (docs/13, ADR-0011). Owner agents (accountant, analyst, business manager) are staff-only, need a role permission (`required_permission`), are bound to one business, and may state only numbers a tool returned. The business manager proposes actions and never applies them.
  - **Customer agents answer from the records too** (docs/13 §5.2–5.3). `ai_agents/tools/facts.py::read_catalog` reads the business once per turn through services: branches, opening hours (the union of providers' working windows), services with descriptions, who performs each one and whether it is bookable, rating, and the cancellation and deposit policy. It goes into the receptionist's and Sara's instructions and is the marketplace's `get_business_details`. Every agent but Sara has `grounded_numbers` on, so a price or hour not in a tool result or the facts is retried once, then handed off. No vector index: the questions are about structured rows.
  - A turn holds no transaction (see "Services `flush()`" above). What a write tool produced for the client comes back in `AiChatResponse.held_slots` and `queue_places`, even with a handoff. The model never sees a hold token.
  - No agent cancels. `request_cancellation` checks the booking against `BookingService.preview_cancellation` and returns it in `pending_cancellations`; the customer confirms through the booking's cancel route.
  - **A promised person must exist.** A signed-in customer's handoff at a business opens a follow-up in `support` (`follow_ups`, staff inbox at `/app/follow-ups`, `view_customers`), one per conversation, and `AiChatResponse.follow_up_opened` says so; only then does the widget say someone will get back to them. With no follow-up (staff, marketplace, a failure), the fallback says the assistant is unavailable instead. Sara opens one per call wherever she says someone will call (`CallCenterService._promise_callback`).
  - **Conversation memory** is in Redis (`ai_agents/history.py`). Recent turns are keyed by tenant, principal, business and a hash of `session_id`, with a TTL and a turn cap. An unreachable Redis gives a fresh turn, never a failed one. Tool results from earlier turns still count as grounded.
  - `tests/modules/ai_agents/` asserts that every other flow works offline. `test_turns.py` runs whole turns against PydanticAI's `FunctionModel`, and conftest gives each test app an in-memory conversation store.
  - Agents call services, never repositories.

### Call center: Sara on the phone (`call_center`, ADR-0017)

- **Unifonic Voice carries the call; NOVA's agent decides what to say.** A call is a loop of webhook turns. Unifonic GETs `/webhooks/voice/{tenant_id}/lines/{line_id}.{hmac}` when a line rings, and POSTs each answer (recognised text, or keys) to `…/calls/{purpose token}`. Both routes are in `PUBLIC_ROUTES` because Unifonic sends no auth header: the URLs are the credentials. The tenant is in the path and scopes RLS before anything is read, so no `bypass_tenant_scope` is needed.
- **`call_center_agent` (alias `sara`) is `voice_only`.** The chat routes refuse her, and the voice path refuses every other agent. She runs through `AiChatService.chat(voice=True)` with the same tools and rules as the chat agents.
- **The keypad decides, never the model** (`call_center/domain.py`):
  - 1 books the held time: `confirm_latest_offer` reads the newest offer's hold token server-side, as the app sends the button's.
  - 2 cancels the booking Sara offered to cancel, for a verified caller only.
  - 3, after she books, gives WhatsApp consent and sends the booking's details (`BookingDetailsRequested` → `booking_received`: branch-local time, ticket link, "the business will confirm"). A customer who already consented gets them without being asked. The booking itself stays a `draft` until staff confirm it.
  - A 4-digit code from WhatsApp verifies the caller.
- **Caller ID only finds the customer to book for.** Customer-service tools refuse with `caller_not_verified` until the code has been typed. A turn acts as a SERVICE principal, so those tools also check that a booking named by id is the customer's own.
- **The router commits before and after `converse`,** so no transaction is held across inference or speech.
- **Her model is `VOICE_AI_*`** (`build_voice_inference_engine`): vLLM too, the `llm` service unless `VOICE_AI_BASE_URL` names a faster vLLM server; one model with a 6 s turn. A timeout makes her ask the caller to repeat.
- **Her voice is Qwen3-TTS.** Qwen ships no Arabic, so it is the Saudi fine-tune `vadimbelsky/qwen3-TTS-KSA`, on an OpenAI-compatible `/audio/speech` server (`VOICE_TTS_*`, `integrations/voice/speech.py`): NOVA's own compose `tts` service (`infra/tts/server.py`, profile `tts`, `http://tts:8091/v1`, ADR-0018), which wraps `qwen-tts` and resamples the model's 24 kHz to the 8 kHz asked for. llama.cpp cannot serve Qwen3-TTS.
  - Clips are cached in Redis under an HMAC key, served at `/webhooks/voice/audio/{key}.wav`, and played by Unifonic.
  - Any failure, timeout or English reply falls back to Unifonic's own `say`, and so does a clip that is not mono PCM WAV at `VOICE_TTS_SAMPLE_RATE` (`wav_problem`) or that Redis could not store.
  - The model and the voice share `VOICE_TURN_BUDGET_SECONDS` per turn; speech gets what the model left.
  - Every reply goes through `CallCenterService.speak`, which applies `core/spoken.py::speakable` (Saudi words for times, riyals and amounts; no markdown, links or emoji).
- **Her words are Saudi dialect in the polite plural** (تبون، اضغطوا). On a call, the tools give the model times as a Saudi says them (`app/core/spoken.py`).
- **Reminder calls** come from the hourly `place_reminder_calls` cron. They need `customers.voice_consent`, run 10:00–21:00 in the branch's timezone, and ring once per booking (a partial unique index). The call row is committed before dialling; only a dial that certainly did not ring (`VoiceGatewayError.may_have_placed` false) removes it for the next sweep.
- **Hung-up calls:** Unifonic sends nothing on a hang-up, so the hourly `end_abandoned_calls` ends a call idle for `CALL_LINK_TTL` (2 h), at its last turn; an unanswered reminder becomes `no_answer`.
- **Retention:** the nightly `scrub_old_calls` clears callers' numbers and Sara's words from calls older than `VOICE_CALL_RETENTION_DAYS` (90), keeping outcomes. Speech below `VOICE_MIN_SPEECH_CONFIDENCE` is asked for again, never sent to the model.
- **Plan feature `ai_call_center`** (Studio, Chain).
- **Unverified until a live Unifonic account:** the field names in `integrations/voice/unifonic.py`, and whether `play` accepts a URL.

### Tests

- **Real Postgres, never SQLite** (ADR-0005).
  - `tests/conftest.py` applies the Alembic migrations once per session, and only for tests that request `db_session`.
  - Each test runs inside an outer transaction (with savepoints) that is rolled back afterwards.
  - Keep every `test_domain.py` DB-free.
- **Fixtures.** `client` overrides `get_db_session` and `get_principal`. The default principal is SERVICE; override the `principal` fixture to test authorization.
- **Factories:** `tenant_factory`, `business_factory`, `location_factory`, `service_factory`, `provider_factory`, `customer_factory`, and `qualify` (assigns a provider to a service).
- **New modules** get `tests/modules/<name>/` with `test_domain.py` (no DB), `test_repository.py` (tenant isolation) and `test_router.py`.

### Frontend (`nova-frontend/`)

- **API layer.** `src/lib/api/<module>.js` mirrors the backend's modules. Every call goes through `http` in `src/lib/api/client.js`, which handles the base URL, auth headers, tenant paths, idempotency keys, a 401 refresh-and-retry, and the error envelope as `ApiError` (plus `NetworkError`).
  - `client.js` never imports the auth store. `stores/auth.svelte.js` injects itself through `configureAuth`, because importing the store would be circular.
  - With `PUBLIC_API_BASE_URL` empty, `src/routes/api/v1/[...path]/+server.js` serves an in-memory mock. `nova-frontend/.env` points it at the real backend on `:8000`.
- **State** lives in universal reactive modules, `src/lib/stores/*.svelte.js`: auth, tenant, business, access, theme, toast. Top-level `$state` in these files needs no context or provider.
  - The JWT decode in `utils/jwt.js` is for display only and is never verification.
  - The refresh token is never in page script. The web app signs in with `refresh_cookie: true`, and the API sets it as an httpOnly, `SameSite=Strict` cookie on `/api/v1/auth` (`auth_router.py`); `POST /auth/refresh` with no token uses the cookie, and `POST /auth/logout` deletes it. Only the 15-minute access token is in localStorage. `client.js` fetches `/auth/*` with `credentials: 'include'`, so an e2e stub for those routes must echo the origin and allow credentials: a browser refuses a wildcard `access-control-allow-origin` on a credentialed response.
  - A Content-Security-Policy is set in `vite.config.js` (`kit.csp`): SvelteKit adds a nonce to its own script, and nothing else inline runs. A new external origin (fonts, scripts, an API host) must be added there, or the browser blocks it.
  - **PWA** (`@vite-pwa/sveltekit`, `SvelteKitPWA` in `vite.config.js`): a manifest, icons generated at build time from `static/Logo.png` (`pwa-assets.config.js`; nothing generated is committed, so replacing that image is the whole change), and a `generateSW` worker registered from `routes/+layout.svelte`. It precaches only static files and `_app/immutable` chunks: SSR pages carry a CSP nonce and the caller's data, so `navigateFallback` is `null` and no HTML or `/api` response is cached. `registerType: 'prompt'` with no prompt UI, so a new worker waits for every tab of the old one to close and never reloads a page. On under `vite dev` too (`devOptions`), so the browser offers to install there: the dev worker (`/dev-sw.js`) precaches one empty file and is generated in the OS temp dir, not `dev-dist/`. `playwright.config.js` sets `serviceWorkers: 'block'`, because `page.route` cannot see a request a worker handles.
  - `accessStore` (`GET /memberships/me`) only hides UI the caller can't use. The backend still enforces every permission.
- **Routes.** Public pages (`/`, `/discover`, `/business`, `/pricing`…) use `SiteHeader`. `/app/*` is the staff dashboard, with its own sidebar shell.
- **i18n (en/ar), no library.** Wrap every user-visible string in `t('English text', {params})` from `$lib/i18n/index.svelte.js`. Use `tp()` for plurals and `m()` for strings kept in constants.
  - Arabic lives in `src/lib/i18n/ar/*.js`, keyed by the English text. These files are JSON bodies (and prettier-ignored) so scripts can merge into them. Backend errors translate by code, as `error.<code>` keys in `ar/errors.js`.
  - The `nova_locale` cookie, else Accept-Language, picks the locale. `hooks.server.js` sets `<html lang dir>` server-side.
  - Chart SVGs and Leaflet containers are forced to `dir="ltr"`.
  - Modules imported by Node-run e2e specs (`lib/map/geolocate.js`, `coordinates.js`) must not import `$lib/i18n`.
- **Design system.** Use the semantic tokens defined in `src/routes/layout.css`: `bg-canvas`/`surface*`, `border-line*`, `text-fg*`, `rounded-control|card|panel`, `shadow-card|raised|overlay`, `focus-ring`. Don't use raw `slate` + `dark:` pairs or new radius and shadow values.
  - Use the primitives in `src/lib/components/ui` (with `ui/styles.js` for fields) and their variants, e.g. `Button size="icon"`, rather than class overrides.
- **Maps** use Leaflet with OpenStreetMap tiles (ADR-0012). The branch form is filled from its pin, never typed: `LocationPicker typing={false}`, and `GET /catalog/places/reverse` (`integrations/geocoding.py`, Nominatim, called by the API with an identifying User-Agent, `GEOCODER_URL`) names the district and city in both languages. `create_location` makes a repeated name's slug unique (`-2`, …).
- `nova-frontend/AGENTS.md` refers to Svelte MCP tools. When they aren't connected, validate with svelte-check and eslint instead.

## Gotchas

- **ADRs can be stale.** Their "Consequences" sections describe the code at the time the ADR was written. ADR-0006, for example, lists RLS, the outbox, rate limiting and idempotency as missing, and all of them exist now. Trust the code.
- **SELinux.** Any bind mount added to `infra/docker-compose.yml` needs the `:z` label, like the existing ones.
- **Compose hardening, keep all of it.**
  - Published ports bind to `127.0.0.1`.
  - Redis requires `REDIS_PASSWORD`.
  - `backend` and `worker` get no schema-owner credentials: compose blanks `POSTGRES_PASSWORD` in them.
  - ARQ jobs are JSON, not pickle (`WorkerSettings.job_serializer`). With pickle, anyone who can write to Redis runs code in the worker.
  - `make infra/.env` copies `infra/.env.example` and fills in every blank secret. The repository is public, so the example must never hold a secret value. Commit `5e70214` once deleted it (and `pnpm-workspace.yaml` and `nova-frontend/.npmrc`, which the frontend Dockerfile copies) under a "docs: formatting" title, which broke `make dev` on a fresh checkout; all three are restored.
- **Dev image.**
  - The venv lives at `/opt/venv` so the `/app` bind mount cannot shadow it.
  - The container UID must match the host's (`UID`/`GID` in `infra/.env`), because `alembic revision` writes into the mount.
  - `nova_backend/uv.lock` is tracked, and the Dockerfile's `uv sync --frozen` needs it. After changing dependencies, run `uv lock` and rebuild `backend`.
- **Formatting.** `make fmt` reformats all of `app` and `tests`, and a few files on main are not format-clean. Scope `ruff format` to the files you changed.
- **Local `infra/.env`** has `ENV=local` and `AUTH_DEV_BYPASS=true`, so a request to `:8000` without a token acts as SERVICE. A 404 or 422 from a guarded route without a token is therefore expected, not a missing guard.
