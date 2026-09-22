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
│   │   ├── catalog/         ✅ Business, Location, Service, Provider
│   │   ├── discovery/       ✅ MarketplaceReferral  ← the only public, cross-tenant slice
│   │   ├── booking/         ✅ Booking, Schedule, SlotHold  ← reference implementation
│   │   ├── queue/           ✅ Queue, QueueEntry, Ticket
│   │   ├── review/          ✅ Review  ← verified 1-5 ratings of completed visits
│   │   ├── payment/         ✅ Payment, Refund
│   │   ├── billing/         ✅ Subscription, CommissionLine, Invoice, Payout
│   │   ├── analytics/       ✅ owner reports and Plotly charts (pandas, numpy)  ← owns no tables
│   │   ├── media/           ✅ MediaAsset
│   │   ├── notification/    ✅ Notification
│   │   └── ai_agents/       ✅ PydanticAI agents (calls services, never the DB)
│   │
│   ├── integrations/        outbound adapters (Moyasar, Nextcloud, WhatsApp)
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

**Pure functions** — `identity`, `catalog`, `discovery`, `review`, `media`, `notification`.
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

## Commands

```bash
make dev        # docker compose up
make migrate    # alembic upgrade head
make test       # pytest
make lint       # ruff check
make fmt        # ruff format
```
