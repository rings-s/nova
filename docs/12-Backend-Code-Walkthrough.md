---
title: Backend Code Walkthrough
created: 2026-08-15
project: NOVA
type: guide
tags: [fastapi, ddd, onboarding, tutorial]
related_code:
  - nova_backend/app/modules/identity/
  - nova_backend/app/modules/booking/
---

# Backend Code Walkthrough

> [!important] Goal
> Understand every file in the backend, and be able to add an endpoint yourself.

Written for a first FastAPI session. Start at the top and read straight through.
The reference map (shorter, no teaching) is `nova_backend/README.md`.

---

## 1. What FastAPI actually does

FastAPI's whole job is: **turn an HTTP request into a Python function call, and turn
what you return back into JSON.**

Here is a complete FastAPI app:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello")
async def hello():
    return {"message": "hi"}
```

`GET /hello` → runs `hello()` → sends back `{"message": "hi"}`. That is it.

Everything else in our codebase exists because a real product needs more than this: database
access, validation, business rules, multi-tenancy. FastAPI does **not** tell you how to organise
that — which is exactly why we needed the structure this document explains.

### The four FastAPI ideas you need

**1. Path operations** — a function bound to a URL and HTTP verb.

```python
@router.post("/tenants")            # POST /tenants
@router.get("/tenants/{tenant_id}") # GET  /tenants/<some-id>
```

`{tenant_id}` in the path becomes an argument in your function.

**2. Pydantic models** — classes that describe and validate data.

```python
class CreateTenantRequest(ApiSchema):
    name_en: str
    phone: str
```

If a request body is missing `phone`, or sends a number where a string belongs, FastAPI rejects
it with a `422` **before your function ever runs**. You never write validation `if`-statements
for shape.

**3. `Depends()` — dependency injection.** This is the one that looks strange at first.

```python
async def create_tenant(
    payload: CreateTenantRequest,
    service: TenantService = Depends(get_tenant_service),
):
```

Read it as: _"before running this function, call `get_tenant_service()` and pass me the result
as `service`."_ You never construct a `TenantService` by hand in a route. FastAPI builds it,
including anything _it_ depends on, recursively.

Why bother? Because in tests we swap one line and the whole chain uses a test database:

```python
application.dependency_overrides[get_db_session] = _override_get_db_session
```

**4. `async` / `await`** — while one request waits on the database, the server handles others.

The rule in practice: if a function does I/O (database, HTTP call), it is `async def`, and you
must `await` it when calling it. Forgetting `await` gives you a coroutine object instead of your
data — a very common first-week bug.

```python
tenant = await self.repository.get(tenant_id)   # ✅
tenant = self.repository.get(tenant_id)         # ❌ returns a coroutine
```

Pure logic with no I/O stays a normal `def`. That is why our whole `domain.py` is sync.

---

## 2. The mental model: four layers

Our backend has four responsibilities. Keeping them apart is the entire design.

```
     HTTP request
          │
          ▼
   ┌─────────────┐
   │  router.py  │  DELIVERY     "a POST arrived, here is the JSON"
   └──────┬──────┘
          ▼
   ┌─────────────┐
   │ service.py  │  APPLICATION  "to create a tenant, do these steps in order"
   └──────┬──────┘
          ▼
   ┌─────────────┐
   │  domain.py  │  DOMAIN       "a phone number must be a GCC number"
   └──────▲──────┘
          │
   ┌──────┴──────┐
   │repository.py│  PERSISTENCE  "SELECT * FROM tenants WHERE ..."
   └─────────────┘
```

**Arrows point inward.** The domain is the centre and depends on nothing. The router knows about
the service; the service knows about the domain; the domain knows about nobody.

Why this direction? Because business rules outlive technology choices. If we replace FastAPI, or
move from PostgreSQL to something else, `domain.py` does not change. And it means our business
rules can be tested with no database and no web server — our 40 domain tests run in **0.02
seconds** for exactly this reason.

> [!tip] The layers are roles, not folders
> There is no top-level `domain/` directory. Each layer appears as a _file_ inside every module.
> One feature = one folder, not four.

---

## 3. The map of the codebase

```
nova_backend/
├── app/
│   ├── main.py          Assembles the app. Read this first — it is short.
│   │
│   ├── core/            Shared things with no business meaning
│   │   ├── config.py      Settings read from environment variables
│   │   ├── deps.py        get_db_session, get_tenant_context
│   │   ├── exceptions.py  DomainError → NotFound / Conflict / Validation
│   │   ├── error_handlers.py  turns those into HTTP responses
│   │   ├── schemas.py     ApiSchema base class
│   │   ├── values.py      Money, TimeRange
│   │   ├── validators.py  phone / slug / bilingual rules
│   │   └── events.py      publish_event
│   │
│   ├── db/              Database plumbing
│   │   ├── base.py        the SQLAlchemy Base class
│   │   ├── mixins.py      reusable columns (id, timestamps, tenant_id)
│   │   ├── session.py     the database connection
│   │   └── repository.py  BaseRepository, TenantScopedRepository
│   │
│   ├── modules/         ⭐ the actual product, one folder per business area
│   │   ├── registry.py    where modules get plugged in
│   │   ├── identity/      ✅ Tenant — the business account
│   │   ├── catalog/       ✅ Business, Location, Service, Provider
│   │   ├── booking/       ✅ Booking — the core
│   │   ├── queue/ payment/ billing/   ✅ tickets, money in, money owed
│   │   └── media/ notification/ ai_agents/   ✅ files, messages, agents
│   │
│   ├── integrations/    talking to the outside world (Moyasar, WhatsApp, Nextcloud)
│   └── worker/          background jobs
│
├── alembic/             database migrations (schema version history)
└── tests/
```

**Where the product lives is `app/modules/`.** Everything else is support.

> [!note] Implemented differences
> The map above leaves out `modules/discovery/`, the public marketplace (ADR-0010),
> `modules/analytics/`, the owner reports and Plotly charts (ADR-0011), and several
> `core/` files: `security.py`, `throttling.py`, `idempotency.py`, `context.py` and
> `middleware.py` (ADR-0006). `nova_backend/README.md` is kept current.

---

## 4. The ten files in a module

Open `app/modules/identity/` — every module has the same files in the same roles. Once you learn
one module, you can navigate all of them.

| File              | Layer       | What you write here                           |
| :---------------- | :---------- | :-------------------------------------------- |
| `__init__.py`     | —           | A summary of the module. **Read this first.** |
| `router.py`       | delivery    | URL endpoints                                 |
| `schemas.py`      | contract    | What JSON goes in and out                     |
| `service.py`      | application | The steps of a use case                       |
| `domain.py`       | **domain**  | The business rules                            |
| `models.py`       | persistence | Database table definitions                    |
| `repository.py`   | persistence | Database queries                              |
| `events.py`       | domain      | Announcements ("a booking was confirmed")     |
| `exceptions.py`   | domain      | This module's errors                          |
| `dependencies.py` | delivery    | Wiring for `Depends()`                        |

### Start with `__init__.py`

Most codebases have empty `__init__.py` files. Ours carry the module's summary:

```python
"""Bounded context: IDENTITY — who the business is.

Aggregates      Tenant
Tables          tenants
Depends on      (nothing — this is the root context)
Status          implemented

Public surface — what other modules may import:
    from app.modules.identity.service import TenantService

Internal — do not import from other modules:
    models.py, repository.py, dependencies.py, router.py
"""
```

That tells you what the module owns and what you are allowed to touch from outside it, before
reading a line of code.

---

## 5. Worked example: creating a tenant

Let's follow one real request through every file.

```bash
curl -X POST http://localhost:8000/api/v1/tenants \
  -H "Content-Type: application/json" \
  -d '{"name_en": "Glow Salon", "name_ar": "صالون جلو", "phone": "+966500000002"}'
```

> [!note] Implemented differences
> Every route now needs `-H "Authorization: Bearer <access token>"`, where the token comes from
> `POST /api/v1/auth/login` (ADR-0006). `POST /tenants` makes the caller the tenant's owner
> (ADR-0007). Locally, `AUTH_DEV_BYPASS=true` treats a request with no header as a service
> principal. It is off in `infra/.env.example`, and the app refuses to start with it outside
> `ENV=local`/`test` or while `CLOUDFLARE_TUNNEL_TOKEN` is set.

### Step 1 — `schemas.py` defines the shape

```python
class CreateTenantRequest(ApiSchema):
    name_en: str = Field(min_length=1, max_length=200)
    name_ar: str = Field(min_length=1, max_length=200)
    phone: str
    default_currency: str = Field(default="SAR", min_length=3, max_length=3)


class TenantOut(ApiSchema):
    id: UUID
    name_en: str
    name_ar: str
    slug: str
    phone: str
    default_currency: str
    created_at: datetime
    updated_at: datetime
```

Two classes, because **what you send is not what you get back**. You send a name; you get back an
id, a generated slug, and timestamps. Never reuse one class for both — it forces you to make
fields optional that are actually required.

FastAPI checks the request against `CreateTenantRequest` before your code runs. Send `name_en: ""` and
you get a `422` for free.

### Step 2 — `router.py` receives it

```python
router = APIRouter(prefix="/tenants", tags=["identity"])


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: CreateTenantRequest,
    session: AsyncSession = Depends(get_db_session),
    service: TenantService = Depends(get_tenant_service),
) -> Tenant:
    tenant = await service.create(**payload.model_dump())
    await session.commit()
    return tenant
```

Line by line:

- `prefix="/tenants"` — every route here starts with `/tenants`. Combined with the `/api/v1`
  added in `main.py`, the full path is `/api/v1/tenants`.
- `response_model=TenantOut` — filters the response through that schema. If `Tenant` ever gains
  a secret column, it cannot leak: anything not in `TenantOut` is stripped.
- `payload: CreateTenantRequest` — FastAPI sees a Pydantic type and knows this is the request body.
- `Depends(...)` — FastAPI supplies the session and service.
- `payload.model_dump()` turns the Pydantic object into a dict; `**` spreads it into arguments.
- `await session.commit()` — **the router commits.** Remember this; §7 explains why.

Notice what is _absent_: no validation, no SQL, no business rules. If you find yourself writing
an `if` about business meaning in a router, it belongs in `service.py` or `domain.py`.

### Step 3 — `dependencies.py` builds the service

```python
def get_tenant_repository(
    session: AsyncSession = Depends(get_db_session),
) -> TenantRepository:
    return TenantRepository(session)


def get_tenant_service(
    repository: TenantRepository = Depends(get_tenant_repository),
) -> TenantService:
    settings = get_settings()
    return TenantService(
        repository,
        allowed_phone_country_codes=settings.allowed_phone_country_codes,
    )
```

A dependency chain: `get_tenant_service` needs a repository, which needs a session. FastAPI walks
this automatically. Your route just asks for the service.

### Step 4 — `service.py` runs the use case

```python
async def create(
    self, *, name_en: str, name_ar: str, phone: str, default_currency: str = "SAR",
) -> Tenant:
    require_bilingual_text(name_en, name_ar)          # ① domain rule
    validate_gcc_phone(phone, self.allowed_phone_country_codes)   # ② domain rule
    slug = generate_slug(name_en)                     # ③ domain rule

    if await self.repository.get_by_slug(slug) is not None:   # ④ ask the database
        raise DuplicateSlugError(slug)

    tenant = Tenant(                                   # ⑤ build the row
        name_en=name_en, name_ar=name_ar, slug=slug,
        phone=phone, default_currency=default_currency,
    )
    self.repository.add(tenant)
    await self.repository.session.flush()              # ⑥ send to DB, no commit

    await publish_event(CreateTenantRequestd(tenant_id=tenant.id))   # ⑦ announce it
    return tenant
```

> [!note] Implemented differences
> The current `create` also takes `owner_user_id`, the authenticated caller, and makes that user
> the owner (ADR-0007). The event call passes the session,
> `await publish_event(session, TenantCreated(...))`, which is how the event lands in the outbox
> inside the same transaction (docs/08 section 16).

This reads like a description of the use case, which is the point. It **sequences** steps; it
does not contain the rules themselves — those are the imported functions in ①②③.

### Step 5 — `domain.py` holds the rules

For `identity`, the rules are plain functions:

```python
def validate_gcc_phone(phone: str, allowed_country_codes: list[str]) -> str:
    match = _E164_PATTERN.match(phone)
    if not match:
        raise ValidationDomainError(
            f"Phone number '{phone}' must be in E.164 format, e.g. +9665XXXXXXXX."
        )
    country_code = match.group(1)
    if country_code not in allowed_country_codes:
        raise ValidationDomainError(
            f"Phone country code '+{country_code}' is not a supported GCC code."
        )
    return phone
```

No FastAPI. No SQLAlchemy. No database. Just a rule you could read aloud to the business owner.

Note it raises `ValidationDomainError`, **not** `HTTPException`. The domain does not know HTTP
exists. Translation happens in `core/error_handlers.py`:

```python
async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )
```

So the client sees `422 {"code": "validation_error", ...}` and the rule stayed framework-free.

> [!note] Implemented differences
> The response is now nested: `422 {"error": {"code": "validation_error", "message": "...",
"field": null, "retryable": false, "correlation_id": "..."}}`. The same handlers render
> constraint violations, request validation failures and uncaught exceptions (ADR-0006).

### Step 6 — `models.py` is the table

```python
class Tenant(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "tenants"

    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    default_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")
```

One class = one table; one attribute = one column. The mixins add shared columns so you do not
retype them: `UUIDPKMixin` gives `id`, `TimestampMixin` gives `created_at` / `updated_at`.

### Step 7 — `repository.py` talks to the database

```python
class TenantRepository(BaseRepository[Tenant]):
    model = Tenant

    async def get_by_slug(self, slug: str) -> Tenant | None:
        stmt = self._base_select().where(Tenant.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
```

All database access lives behind this. The service never writes SQL; it asks the repository. That
means we can test the service against a fake repository, and change how we query without touching
business logic.

### The full round trip

```
POST /api/v1/tenants
  → main.py            matches the route
  → router.py          validates body against CreateTenantRequest
  → dependencies.py    builds TenantService (+ repository + session)
  → service.py         orchestrates the steps
  → domain.py          enforces the rules      ← raises here if invalid
  → repository.py      SELECT then INSERT
  → router.py          commits
  → response_model     filters output through TenantOut
201 Created
```

---

## 6. The three files that look alike

This confuses everyone at first. `schemas.py`, `models.py`, and `domain.py` can all describe "a
booking" — but they answer different questions.

|              | Question it answers                  | Changes when…                    |
| :----------- | :----------------------------------- | :------------------------------- |
| `schemas.py` | What does the API accept and return? | the mobile app needs a new field |
| `models.py`  | How is it stored in PostgreSQL?      | we add an index or column        |
| `domain.py`  | What is _true_ about it, always?     | the business changes its rules   |

Concretely, in `booking`:

```python
# schemas.py — what the client sends
class CreateBookingRequest(ApiSchema):
    service_id: UUID
    starts_at: datetime

# models.py — the table row
class BookingRecord(Base, ...):
    __tablename__ = "bookings"
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

# domain.py — the business object
class Booking:
    def confirm(self) -> None: ...
```

Why not one class for all three? Because the client must not be able to set `status`, and the
database must not dictate business rules. Keeping them separate is what lets each change
independently.

> [!tip] A useful smell
> If you are tempted to add an API-only field to `models.py`, or a database concern to
> `schemas.py`, you have found the boundary. Add it to the right file instead.

---

## 7. Who commits? (the transaction rule)

**Services flush. Routers commit.**

- `flush()` sends SQL to the database but does not finalise it. Still undoable.
- `commit()` makes it permanent.

Because only the router commits, one endpoint can call several services and they all succeed or
all fail together:

```python
booking = await booking_service.create(...)   # flushed
await payment_service.create_intent(...)      # flushed
await session.commit()                        # both become real, together
```

If the payment step raises, the booking is never written. Had the booking service committed on
its own, you would have a booking with no payment — corrupt data that is painful to clean up.

---

## 8. Two kinds of `domain.py`

You asked specifically about the domain files. They come in two shapes, and knowing which to
write is the main judgement call in this codebase.

### Shape A — pure functions (`identity`, `catalog`)

Used when the rules are about **field values**.

```python
def validate_service_duration(duration_minutes: int) -> int:
    if duration_minutes < MIN_SERVICE_DURATION_MINUTES:
        raise ValidationDomainError(...)
    if duration_minutes % 5 != 0:
        raise ValidationDomainError("Service duration must be a multiple of 5 minutes.")
    return duration_minutes
```

Here the ORM model _is_ the business object. No extra class.

### Shape B — a rich entity (`booking`, `queue`, `payment`)

Used when the thing has a **lifecycle that can be corrupted**.

A booking moves through states, and only some moves are legal:

```
DRAFT ──▶ PENDING_PAYMENT ──▶ CONFIRMED ──▶ CHECKED_IN ──▶ IN_SERVICE ──▶ COMPLETED
```

So `booking/domain.py` defines a class where the transitions are the only way to move:

```python
_ALLOWED_TRANSITIONS = {
    BookingStatus.CONFIRMED: frozenset(
        {BookingStatus.CHECKED_IN, BookingStatus.CANCELLED, BookingStatus.NO_SHOW}
    ),
    BookingStatus.CHECKED_IN: frozenset({BookingStatus.IN_SERVICE}),
    ...
}


class Booking:
    def _transition_to(self, target: BookingStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise InvalidBookingTransition(self.status, target)
        self.status = target

    def confirm(self) -> None:
        self._transition_to(BookingStatus.CONFIRMED)
```

There is no `booking.status = "completed"` anywhere. You cannot skip check-in even by accident:

```python
booking = Booking(..., status=BookingStatus.CONFIRMED)
booking.complete()   # raises InvalidBookingTransition
```

### How to decide

Ask: **can this thing be in a wrong state?**

- A service with a negative price → rejected once, at the edge. **Shape A.**
- A booking marked `COMPLETED` that was never `CHECKED_IN` → a corrupted object that will
  mislead every report forever. **Shape B.**

Shape B costs you a mapping layer (`repository.py` converts between `domain.Booking` and
`BookingRecord`). Pay it only where a lifecycle exists.

---

## 9. Multi-tenancy — the rule that must never break

Many salons share one database. Salon A must never see salon B's data.

Every table except `tenants` carries a `tenant_id`, and its repository extends
`TenantScopedRepository`, which filters **every** query:

```python
def _scope(self, stmt: Select) -> Select:
    return stmt.where(self.model.tenant_id == self.tenant_id)
```

The important design detail: there is **no unscoped query method** on that base class to reach
for by mistake. You cannot forget the filter, because there is no version without it.

And `tenant_id` comes only from the URL path:

```python
async def get_tenant_context(tenant_id: UUID = Path(...)) -> UUID:
    return tenant_id
```

Never from the request body — otherwise a caller could simply ask for someone else's data.

> [!note] Implemented differences
> `get_tenant_context` no longer returns the path value unchecked, and it does three things:
>
> 1. It requires `require_tenant_access`: a missing token is a 401, and a staff member of another
>    tenant gets a 403.
> 2. It sets `app.current_tenant_id` for Postgres Row-Level Security.
> 3. It stamps the request's log context (ADR-0006).
>
> The known gap mentioned next is closed: RLS is enabled and forced on every tenant-owned table
> (ADR-0003). A customer principal can reach every tenant, because NOVA is a marketplace, so
> operational routes add `require_staff`. Routes that move money or read what a business earns
> add a role permission instead, read from this tenant's `memberships` (`RequirePermission`).
>
> `get_tenant_context` now builds on `get_authorized_tenant`, which does steps 1 and 3 without
> touching the database. The AI chat depends on that alone, because a turn holds no request
> transaction.

See `docs/decisions/0003-tenant-isolation-strategy.md`, including the known gap (this is an
application-layer control, not a database one).

---

## 10. Where do I put this?

| I want to…                                | File                      |
| :---------------------------------------- | :------------------------ |
| Add a new URL                             | `router.py`               |
| Add a field to a request/response         | `schemas.py`              |
| Add a rule like "price can't be negative" | `domain.py`               |
| Add a database column                     | `models.py` + a migration |
| Add a query                               | `repository.py`           |
| Change the order of steps in a use case   | `service.py`              |
| Add a new error type                      | `exceptions.py`           |
| Tell other modules something happened     | `events.py`               |

**Cross-module rule:** call the other module's _service_, never its repository or models.

```python
service = await self.catalog.get_service(service_id)      # ✅
stmt = select(catalog.models.Service).where(...)          # ❌
```

For reactions rather than questions, publish an event: booking publishes `BookingConfirmed`, and
notification reacts. Booking must not import notification.

---

## 11. Your turn: add an endpoint

Add `GET /api/v1/tenants/by-slug/{slug}` returning a tenant by its slug.

1. **`repository.py`** — already done, `get_by_slug` exists. Reuse it.
2. **`service.py`** — add a method:
   ```python
   async def get_by_slug(self, slug: str) -> Tenant:
       tenant = await self.repository.get_by_slug(slug)
       if tenant is None:
           raise TenantNotFoundError(slug)
       return tenant
   ```
3. **`router.py`** — add the route:
   ```python
   @router.get("/by-slug/{slug}", response_model=TenantOut)
   async def get_tenant_by_slug(
       slug: str,
       service: TenantService = Depends(get_tenant_service),
   ) -> Tenant:
       return await service.get_by_slug(slug)
   ```
4. **Check it** — open `http://localhost:8000/docs`. FastAPI generates interactive documentation
   from your code; your new endpoint is there and you can call it from the browser.

Note you touched no schema and no model. That is the structure working.

> [!note] Implemented differences
> Add `principal: Principal = Depends(get_principal)` to the route as well. NOVA fails closed, so
> every route authenticates (ADR-0006), and `tests/test_route_guards.py` fails the build when one
> doesn't.

> [!warning] Route order matters
> Register `/by-slug/{slug}` **before** `/{tenant_id}`. FastAPI matches top to bottom, so
> `/{tenant_id}` would otherwise swallow `by-slug` and try to parse it as a UUID.

---

## 12. Running it

```bash
cd nova_backend
make dev                  # start everything with Docker
make migrate              # apply database migrations
make test                 # run the test suite
make lint                 # check code style
```

Then open **`http://localhost:8000/docs`** — the interactive API documentation, generated from
your code. It is the fastest way to explore what exists.

### Tests worth reading

- `tests/modules/booking/test_domain.py` — pure business rules, no database. Run in 0.02s.
- `tests/modules/catalog/test_repository.py` — proves salon A cannot read salon B's data.
- `tests/test_architecture.py` — parses the code and **fails the build** if a layer imports
  something it shouldn't. The rules in this document are enforced, not just described.

---

## 13. Mistakes to expect in week one

| Mistake                               | What happens                   | Fix                               |
| :------------------------------------ | :----------------------------- | :-------------------------------- |
| Forgetting `await`                    | You get a coroutine, not data  | `await` every async call          |
| SQL in `router.py`                    | Business rules get bypassed    | Move it to `repository.py`        |
| Importing `sqlalchemy` in `domain.py` | `test_architecture.py` fails   | Keep the domain pure              |
| Committing inside a service           | Partial writes on failure      | Only routers commit               |
| One schema for request + response     | Fields become wrongly optional | Split `CreateXRequest` and `XOut` |
| Reading another module's models       | Boundaries collapse            | Call its service                  |
| Raising `HTTPException` in domain     | Domain becomes web-coupled     | Raise a `DomainError`             |

---

## 14. Where to go next

1. Read `nova_backend/app/main.py` — it is 50 lines and shows how everything assembles.
2. Read `app/modules/identity/` end to end — the smallest complete module.
3. Read `app/modules/booking/domain.py` — the most interesting business logic we have.
4. Then `nova_backend/README.md` for the condensed reference.

Related: [[02-Backend-FastAPI-DDD-Structure]] · [[06-Domain-Models-and-Aggregates]] ·
[[07-Pydantic-Schemas-and-API-Contracts]] · [[08-Database-Models-and-Persistence]]
