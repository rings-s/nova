# NOVA Backend — Code Structure

How this codebase is organised and where to put new code.
Architecture rationale lives in `docs/02-Backend-FastAPI-DDD-Structure.md`.

## The one rule

Dependencies point **inward**. The domain is the centre and knows nothing about the outside.

```
router.py  ──▶  service.py  ──▶  domain.py  ◀──  repository.py
   HTTP          use cases        the rules        persistence
```

| Layer           | May import                          | Must never import        |
| :-------------- | :---------------------------------- | :----------------------- |
| `router.py`     | schemas, service, dependencies      | models, repository       |
| `service.py`    | domain, repository, models, events  | fastapi                  |
| `domain.py`     | stdlib, pydantic, `app.core.values` | fastapi, sqlalchemy      |
| `repository.py` | models, `app.db`                    | fastapi, service         |
| `models.py`     | sqlalchemy, `app.db`                | fastapi, service, domain |

If you are unsure which layer a file is, open it — every file starts with a
header naming its layer and its import rule.

## Where everything lives

```
nova_backend/
├── app/
│   ├── main.py              app factory, middleware, router registration
│   │
│   ├── core/                shared kernel — no business rules
│   │   ├── config.py        Settings from env
│   │   ├── deps.py          get_db_session, get_tenant_context
│   │   ├── exceptions.py    DomainError → NotFound/Conflict/Validation
│   │   ├── error_handlers.py  turns DomainError into an HTTP response
│   │   ├── schemas.py       ApiSchema, Page, ErrorResponse
│   │   ├── values.py        Money, TimeRange       (pure domain)
│   │   ├── validators.py    phone, slug, bilingual (pure domain)
│   │   ├── events.py        publish_event + DomainEvent base
│   │   ├── pagination.py    PageParams
│   │   └── logging.py
│   │
│   ├── db/                  persistence kernel
│   │   ├── base.py          DeclarativeBase + constraint naming convention
│   │   ├── mixins.py        UUIDPK, Timestamp, TenantOwned, SoftDelete
│   │   ├── session.py       async engine and sessionmaker
│   │   └── repository.py    BaseRepository, TenantScopedRepository
│   │
│   ├── modules/             one folder per bounded context
│   │   ├── registry.py      the single place every module is wired in
│   │   ├── identity/        ✅ Tenant, User, Membership, Customer
│   │   ├── catalog/         ✅ Business, Location, Service, Provider, BusinessPhoto
│   │   ├── discovery/       ✅ MarketplaceReferral  ← the only public, cross-tenant slice
│   │   ├── booking/         ✅ Booking, Schedule, SlotHold  ← reference implementation
│   │   ├── queue/           ✅ Queue, QueueEntry, Ticket
│   │   ├── review/          ✅ Review  ← verified 1-5 ratings of completed visits
│   │   ├── payment/         ✅ Payment, Refund
│   │   ├── billing/         ✅ Subscription, CommissionLine, Invoice, Payout
│   │   ├── analytics/       ✅ owner reports and Plotly charts (pandas, numpy)  ← owns no tables
│   │   ├── notification/    ✅ Notification
│   │   └── ai_agents/       ✅ PydanticAI agents (calls services, never the DB)
│   │
│   ├── integrations/        outbound adapters (Moyasar, WhatsApp) + images.py, storage/ (photos)
│   └── worker/              outbox dispatcher + scheduled jobs (ARQ)
│
├── alembic/                 migrations
└── tests/                   mirrors app/modules/
```

✅ implemented · ⬜ scaffolded, not yet implemented

All eleven contexts are implemented. The agent roster (receptionist, customer service,
accountant, analyst, business manager) and the charts are specified in docs/13 and ADR-0011.
`ai_agents` needs the optional `ai` extra and a reachable
Ollama to do inference; it degrades to a human handoff without them, and every other flow is
unaffected (docs/10 section 12).

## Anatomy of a module

Every module under `app/modules/` has the same files, in the same roles.
Open any module and you already know your way around it.

The exception is `analytics`, which owns no tables. It has no `models.py`, `repository.py` or
`events.py`. It reads other modules' fact projections through their services, and adds
`metrics.py` (pandas and numpy, the only place they are imported) and `charts.py` (Plotly).

| File              | Layer       | Holds                                             |
| :---------------- | :---------- | :------------------------------------------------ |
| `__init__.py`     | —           | context summary: aggregates, deps, public surface |
| `router.py`       | delivery    | FastAPI endpoints. No business rules.             |
| `schemas.py`      | contract    | Pydantic request/response DTOs                    |
| `service.py`      | application | use-case orchestration; flushes, never commits    |
| `domain.py`       | **domain**  | the rules. No framework imports.                  |
| `models.py`       | persistence | SQLAlchemy ORM tables                             |
| `repository.py`   | persistence | queries, tenant-scoped                            |
| `events.py`       | domain      | domain event dataclasses                          |
| `exceptions.py`   | domain      | module errors, subclassing `DomainError`          |
| `dependencies.py` | delivery    | FastAPI DI providers                              |

Three of these are not the same thing, and mixing them is the most common mistake:

- `schemas.py` is the **API boundary** — what the outside world sends and sees.
- `models.py` is **infrastructure** — table shape.
- `domain.py` is the **model** — the rules that must hold regardless of either.

## Two styles of `domain.py`

Not every module earns a rich domain entity. We pay for the mapping layer only
where there is a real lifecycle to protect.

**Pure functions** — `identity`, `catalog`, `discovery`, `review`, `notification`.
Rules are field-level validation; the ORM model _is_ the domain object.

```python
def validate_service_duration(duration_minutes: int) -> int: ...
```

**Rich entities** — `booking`, `queue`, `payment`, `billing`.
These own a state machine, so the entity is defined in `domain.py` independent
of the ORM, and the repository maps between them.

```python
class Booking:
    def confirm(self) -> None:
        if self.status not in (BookingStatus.DRAFT, BookingStatus.PENDING_PAYMENT):
            raise InvalidBookingTransition(self.status, BookingStatus.CONFIRMED)
        self.status = BookingStatus.CONFIRMED
```

The test: _can this thing be in a wrong state?_ A service with a bad price is
rejected at the edge. A booking that is `COMPLETED` without ever being
`CHECKED_IN` is a corrupted aggregate — that needs an entity.

## Tracing one request

`POST /api/v1/tenants/{tenant_id}/catalog/services`

1. `main.py` matched the route from `modules/registry.py`.
2. `catalog/router.py` validates the body into `CreateServiceRequest`.
3. `core/deps.py::get_tenant_context` reads `tenant_id` **from the path only**.
4. `catalog/dependencies.py` builds `CatalogService` with repositories already
   scoped to that tenant.
5. `catalog/service.py::create_service` calls `get_location` (proving the
   location belongs to this tenant), then the `domain.py` validators.
6. On a broken rule, `domain.py` raises `ValidationDomainError` — not an
   `HTTPException`. `core/error_handlers.py` turns it into a 422.
7. The repository adds the row; the service flushes.
8. The **router** commits. Services never commit, so one endpoint can compose
   several service calls atomically.

## Multi-tenancy

Every table except `tenants` carries `tenant_id` via `TenantOwnedMixin`, and
every repository for those tables extends `TenantScopedRepository`, which has
no unscoped query method to reach for by mistake.

`tenant_id` is fixed at repository construction from the URL path. It is never
read from a request body or query parameter.

Postgres Row-Level Security backs this up (migration `d4e5f6a7b8c9`): each
request sets `app.current_tenant_id` on its connection and every policy compares
against it, so a connection that never sets it sees nothing. It fails closed.
See `docs/decisions/0003-tenant-isolation-strategy.md`.

**The one exception is `discovery`** (ADR-0010). A customer searching for a
salon has no tenant yet, so the marketplace reads _across_ tenants through
`catalog`'s `PublicCatalogService` and a second RLS window,
`app.discovery_mode`. That window is narrower than it sounds: `FOR SELECT` only,
and matching only rows a business has published — active, listed, not deleted.
Nothing on that path can write across tenants, and an unlisted salon is
invisible to the database rather than merely filtered by the query.

A Postgres **superuser bypasses RLS entirely**, even with `FORCE`, and so does a
`BYPASSRLS` role. The API and worker therefore connect as `nova_app`, which is
neither (migration `e1f2a3b4c5d6`), and only migrations run as the schema owner
(`MIGRATION_DATABASE_URL`). A staging or production process connected as an
exempt role refuses to start (`app.db.session.enforce_rls_role`). The test suite
runs as `nova_app` too, so every run exercises the policies.

## Adding a module

1. Copy the file set above into `app/modules/<name>/`.
2. Write `__init__.py` first — naming the aggregates and the public surface
   forces the boundary decision before any code exists.
3. Use `TenantOwnedMixin` + `TenantScopedRepository` unless it is the tenant root.
4. Register it in `app/modules/registry.py` (models import + router).
5. `uv run alembic revision --autogenerate -m "..."`, then **read the migration**.
6. Add `tests/modules/<name>/` with `test_domain.py` (no DB), `test_repository.py`
   (tenant isolation), `test_router.py` (end-to-end).

## Cross-module calls

Modules talk through **services**, never through each other's repositories or
models. Booking needs a service's duration, so it calls
`CatalogService.get_service()` — it does not import `catalog.models.Service`
and query it.

For anything that is a reaction rather than a question, publish a domain event
instead: booking publishes `BookingConfirmed`; notification reacts. Booking must
not import notification.

## Payments (Moyasar)

Payments go through [Moyasar](https://docs.moyasar.com/), following its API
reference. The adapter is `app/integrations/payments/moyasar.py`; the rules
are in `modules/payment`.

**The flow**

1. `POST /tenants/{id}/payments/intents` opens a Moyasar **invoice**
   (`POST /v1/invoices`) for the booking's price, in halalas, so the server
   decides the amount.
2. With `MOYASAR_PUBLISHABLE_KEY` set, the response's `checkout` holds the
   options for Moyasar's
   [Payment Form](https://docs.moyasar.com/guides/card-payments/basic-integration)
   (`moyasar-payment-form`, `Moyasar.init`), bound to that invoice by
   `invoice_id`. The booking page renders it (`MoyasarForm.svelte`), offering
   mada, Visa, Mastercard and STC Pay. Card details go from the browser straight
   to Moyasar, and Moyasar refuses a form payment whose amount differs from the
   invoice's. Without the key, `redirect_url`, the invoice's hosted page, is
   the fallback. Apple Pay is not enabled in the form: it needs the domain
   verified with Moyasar and Apple's script allowed by the CSP.
3. After 3-D Secure, Moyasar sends the payer to the `return_url` the client
   gave, with `payment=<id>` added (and, from the form, Moyasar's own `id`,
   `status` and `message`, none of them trusted). The page calls
   `POST …/payments/{id}/sync`, which
   fetches the invoice and its payment from Moyasar and captures only if the
   status is `paid` and the amount, currency and invoice all match. The redirect
   itself proves nothing.
4. Moyasar also sends a `payment_paid` webhook to `POST /api/v1/webhooks/moyasar`.
   It is authenticated by the `secret_token` in its body, deduplicated by event
   id, and checked against Moyasar's record of the payment just like a sync.
   Either path confirms the booking; whichever arrives second changes nothing.

A declined card does not fail the payment while the checkout is still open,
because the payer can try another card. The payment fails once the invoice
expires (`MOYASAR_CHECKOUT_TTL_MINUTES`, default 30) or is cancelled.

**Setting it up**

1. In the [Moyasar dashboard](https://dashboard.moyasar.com), under Settings >
   API Keys, copy the **secret** key and the **publishable** key. Use the test
   pair (`sk_test_…`, `pk_test_…`) until go-live. The app refuses to start with
   a `pk_…` key as `MOYASAR_API_KEY` or an `sk_…` key as
   `MOYASAR_PUBLISHABLE_KEY`, with a test and a live key mixed, and with any
   test key when `ENV=production`.
2. Under Settings > Webhooks, add
   `https://<your public host>/api/v1/webhooks/moyasar` with a shared secret of
   your choosing (`openssl rand -hex 32`). Subscribe to at least
   `payment_paid` and `payment_failed`.
3. Set them in `infra/.env` and restart the stack (`make dev`):

   ```dotenv
   MOYASAR_API_KEY=sk_test_...
   MOYASAR_PUBLISHABLE_KEY=pk_test_...
   MOYASAR_WEBHOOK_SECRET=<the webhook's shared secret>
   ```

4. `PUBLIC_APP_URL` must be the customer app's origin. A `return_url`
   anywhere else is refused.

Without a key, payment routes answer 503 `integration_not_configured`, and the
rest of the app runs as normal. Locally, Moyasar cannot reach your webhook
unless you expose it (`make tunnel`). Payments still confirm through the sync
step when the payer returns. To test, pay with Moyasar's
[test cards](https://docs.moyasar.com/guides/card-payments/test-cards/).

A `live: false` (test-mode) webhook is ignored when `ENV=production`. Refunds
go through `POST …/payments/{id}/refund` (owners and managers). A refund made
in Moyasar's dashboard is not synced back to NOVA.

## AI agents (local models)

The agents in `modules/ai_agents` run on a model server on your own machine,
through PydanticAI. The roster, tools and guardrails are in docs/10 and docs/13.
The server connection is in `runtime.py`, and nothing else in the app knows
which server is running.

**Where agents appear**

- `/app/ai` in the dashboard: the accountant, analyst and business manager
  agents, for the business being managed. The list shows only the agents this
  role's permissions allow. Charts and proposed actions come from the tools.
- The storefront (`/discover/<slug>`): an "Ask the assistant" button that opens
  the receptionist agent for signed-in customers.
- `/discover`: the marketplace assistant (`POST /discovery/ai/chat`, customers
  only). It searches every listed business, holds a time, and books at the one
  the customer picks, attributed to the marketplace.
- Both assistants **book for the customer in two turns** (ADR-0015). A hold tool
  offers a time; `book_held_slot` books it only in a later turn, after the
  customer presses its "Yes, book it" (`confirm_hold_token`), and returns the booking's **QR ticket** in `tickets`. The
  booking is a `draft` until the business confirms it. Customers see the QR in
  the chat and under My bookings ("Show ticket"). The business scans it at
  `/app/check-in`, by camera or by pasting the code.
- Both call `GET /tenants/{id}/ai/agents` first. Its `inference_available` is
  false when the model server does not answer. The storefront then hides the
  button, and `/app/ai` shows an "offline" panel.

**Setting it up with LM Studio**

1. In LM Studio, download models that support tool calling. Without a GPU,
   use small Qwen3 models: `lms get qwen/qwen3-4b` for reasoning and
   `lms get qwen/qwen3-1.7b` for routing. Then start the server on all
   interfaces, so the containers can reach it: `lms server start --bind 0.0.0.0 --port 1234` (or turn on "Serve on
   Local Network" in the Developer tab). Keep the host firewall closed to the
   LAN on port 1234. Docker's bridge reaches it through `host.docker.internal`,
   which compose maps with `extra_hosts: host-gateway`.
2. Set the provider in `infra/.env`, then recreate `backend` and `worker`:

   ```dotenv
   AI_PROVIDER=lmstudio
   AI_BASE_URL=http://host.docker.internal:1234/v1
   AI_ROUTING_MODEL=qwen/qwen3-1.7b   # LM Studio's model id (`lms ls`)
   AI_REASONING_MODEL=qwen/qwen3-4b
   AI_REQUEST_TIMEOUT_SECONDS=300      # the 30 s default suits a GPU, not a laptop
   ```

For Ollama, set `AI_PROVIDER=ollama` and point `AI_BASE_URL` (or
`OLLAMA_BASE_URL`) at `http://host.docker.internal:11434/v1`.

**Speed**

A turn sends the agent's instructions and tool schemas, typically 1,000 to 3,000
tokens, and may call the model several times. `AI_THINKING=false`, the default,
adds Qwen3's `/no_think` switch to the instructions. That cut a small
tool-calling turn from 319 s to 59 s with qwen3-8b in LM Studio. PydanticAI's
generic `thinking=False` (sent as `reasoning_effort`) did not finish that turn
within 10 minutes in testing, so it is not used.

Measured on a CPU-only laptop (i7-1185G7, 16 GB, AVX2 runtime), in tokens per
second:

| Model      | Reading the prompt | Generating |
| ---------- | ------------------ | ---------- |
| qwen3-8b   | ~2                 | ~1         |
| qwen3-4b   | ~4.5               | ~1.9       |
| qwen3-1.7b | ~10–27             | ~3–14      |

Only qwen3-1.7b finishes a grounded staff turn there: the accountant's "How much
did we earn this month?" took 270 s over 3–4 model calls, with a real chart.
That machine runs 1.7B in both roles, with `AI_REQUEST_TIMEOUT_SECONDS=600`.
With a GPU, use `qwen/qwen3-4b` or larger for `AI_REASONING_MODEL`.

Load the model with **one parallel slot**, so each follow-up call in a turn
reuses the cached prompt instead of reading it all again (that alone cut a
second call from 1,375 prompt tokens to 253):

```bash
lms load qwen/qwen3-1.7b --parallel 1 -c 8192
```

When the model is unreachable or times out, the turn hands off to a human. It
never fails the request, and the rest of the app is unaffected.

## Commands

```bash
make dev        # docker compose up
make migrate    # alembic upgrade head
make test       # pytest
make lint       # ruff check
make fmt        # ruff format
```
