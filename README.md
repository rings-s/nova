# NOVA

GCC-focused AI booking and customer-operations platform. Initial vertical: beauty centers,
salons, spas, massage centers, and wellness businesses. Connects Customer ↔ Business ↔ Service
Provider for discovery, booking, payments, virtual QR tickets, walk-in queues, WhatsApp
communication, and AI-assisted support/sales/retention.

## Backend Structure — Pragmatic DDD

The backend is organized as **vertical slices**: one folder per bounded context, each holding its
own domain, service, schema, model, and repository files. See `docs/02-Backend-FastAPI-DDD-Structure.md`.

```
nova_backend/
├── app/
│   ├── main.py             # 🚀 FastAPI app factory, middleware, CORS
│   ├── core/               # 🔧 Shared kernel (config, deps, errors, values)
│   ├── db/                 # 🔌 Persistence kernel (base, mixins, repository)
│   ├── modules/            # 📦 Vertical slices (one per bounded context)
│   │   ├── identity/       #    ✅ tenants, users, memberships, customers
│   │   ├── catalog/        #    ✅ businesses, locations, services, providers
│   │   ├── booking/        #    ✅ availability, holds, lifecycle — reference module
│   │   ├── queue/          #    ✅ walk-ins, QR tickets, check-in
│   │   ├── payment/        #    ✅ deposits, Moyasar webhooks, refunds
│   │   ├── billing/        #    ✅ plans, commission, invoices, payouts
│   │   ├── media/          #    ✅ Nextcloud-backed metadata
│   │   ├── notification/   #    ✅ WhatsApp, consent, quiet hours
│   │   └── ai_agents/      #    ✅ PydanticAI agents + guardrails (optional extra)
│   ├── integrations/       # 🔌 Outbound adapters (Moyasar, Nextcloud, WhatsApp)
│   └── worker/             # 🔄 Outbox dispatcher + scheduled jobs (ARQ)
├── alembic/                # 🗄️ Migrations
└── tests/
```

**Full structure guide: [`nova_backend/README.md`](nova_backend/README.md)** — dependency rules,
module anatomy, and a traced request.

### Anatomy of a Module

Every module under `app/modules/` contains the same files:

```
booking/
├── __init__.py             # 🧭 Context summary — aggregates, deps, public surface
├── router.py               # 🌐 API — FastAPI endpoints
├── schemas.py              # 📦 Contracts — Pydantic request/response DTOs
├── service.py              # ⚙️ Application — use case orchestration
├── domain.py               # 💎 Domain — entities, value objects, rules (pure Python)
├── models.py               # 🗄️ Persistence — SQLAlchemy ORM models
├── repository.py           # 🔌 Persistence — DB queries behind an interface
├── events.py               # 📡 Domain events (BookingConfirmed, SlotReleased)
├── exceptions.py           # ⚠️ Module errors, subclassing DomainError
└── dependencies.py         # 🔧 FastAPI DI providers
```

Read `__init__.py` first — it names the aggregates and states what the rest of the system is
allowed to import from the module.

**Dependency rule:** `router.py` ➡️ `service.py` ➡️ `domain.py` ⬅️ `repository.py`.
The domain knows nothing about FastAPI, SQLAlchemy, or PydanticAI. Schemas are API boundary
models, ORM models are infrastructure — neither is the domain model.

### Modules

| Module | Aggregates | Responsibility |
| :--- | :--- | :--- |
| `identity` | `Tenant`, `User`, `Membership`, `Customer` | Who everyone is: the tenant root, sign-in accounts, and the people a salon books |
| `catalog` | `Business`, `Location`, `Service`, `Provider` | Storefronts, branches, bookable services |
| `booking` | `Booking`, `Schedule`, `AvailabilitySlot`, `SlotHold` | Deterministic availability and booking lifecycle |
| `queue` | `Queue`, `QueueEntry`, `Ticket` | Walk-in queues on one timeline with appointments, and QR check-in |
| `payment` | `Payment`, `Refund` | Deposits, captures and refunds via verified Moyasar webhooks |
| `billing` | `Subscription`, `CommissionLine`, `Invoice`, `Payout` | The commercial model: plans, commission on marketplace introductions, monthly invoices, daily payouts |
| `media` | `MediaAsset` | Nextcloud-backed media metadata (references only) |
| `notification` | `Notification` | WhatsApp messages, gated on consent and quiet hours |
| `ai_agents` | — | PydanticAI agents and tools; calls services, never the DB. Optional extra |

Full domain, schema, and persistence specifications live in `docs/`.




## Running it

```bash
make dev                              # creates infra/.env with random secrets, then
                                      # starts postgres, redis, backend, worker
make migrate                          # apply migrations
make test                             # run the suite in a one-off tools container
```

Then open **http://localhost:8000/docs**.

Without Docker, with postgres and redis on localhost:

```bash
make check        # lint + typecheck + the app assembles
make test-local   # the full suite
```

The **worker is load-bearing**, not optional: it drains the transactional outbox. With no
worker running, domain events accumulate undelivered and no customer is ever notified of
anything.

AI agents are an optional extra — `uv sync --extra ai` (or `make image EXTRAS=ai` for the
production image) plus a reachable Ollama. The roster and charts are in
`docs/13-Business-Agents-and-Analytics.md`. Every other
flow works with the inference engine offline, which `tests/modules/ai_agents/` asserts.
