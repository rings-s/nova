# NOVA

> Booking, walk-in queues, deposits and WhatsApp messaging for salons, spas and wellness
> businesses in the GCC, with a marketplace where customers find them.

A salon in Riyadh usually runs its day across a paper book, a WhatsApp chat and a card terminal.
NOVA puts that day in one place: customers find the salon on the marketplace or its own booking
link, book a slot or join the walk-in queue, pay a deposit, and check in with a QR ticket. The
salon runs its calendar, queue, team and money from one dashboard, in English or Arabic.

## Quick start

**You need** Docker with Compose v2, and `make`. Nothing else runs on the host.

```bash
git clone git@github.com:rings-s/nova.git && cd nova
make dev
```

The first run creates `infra/.env` from `infra/.env.example` with fresh random secrets, builds the
images, applies the database migrations, and starts everything. When the logs settle:

| Open                                              | What you get                                          |
| ------------------------------------------------- | ----------------------------------------------------- |
| [localhost:5173](http://localhost:5173)           | The app: marketplace, customer pages, staff dashboard |
| [localhost:8000/docs](http://localhost:8000/docs) | The API, interactive (Swagger UI)                     |

Use `localhost`, not `127.0.0.1`: the API allows browser requests from `localhost:5173` only.

To see the business side, register at `/register`, create a business at `/business/new`, and
you land in the dashboard at `/app` as its owner.

> [!tip]
> The API refuses requests without a token. To try routes from `/docs` or `curl` without signing
> in, set `AUTH_DEV_BYPASS=true` in `infra/.env` and restart (`make down && make dev`). The app
> refuses to start with it outside `ENV=local`/`test`.

The containers run as uid/gid 1000 and write into your checkout (`make revision` creates migration
files there). If `id -u` or `id -g` prints something else, set `UID` and `GID` in `infra/.env` to
match before the first `make dev`.

## What's in the repository

| Path             | What it is                                                                               |
| ---------------- | ---------------------------------------------------------------------------------------- |
| `nova_backend/`  | The API and the background worker: FastAPI, SQLAlchemy (async), PostgreSQL, ARQ on Redis |
| `nova-frontend/` | The web app: SvelteKit 2 and Svelte 5, JavaScript with JSDoc types, Tailwind 4           |
| `infra/`         | The Docker Compose stack `make dev` runs, and `infra/.env.example`                       |
| `docs/`          | Design documents, the threat model, and architecture decision records (ADRs)             |

The stack is PostgreSQL, Redis, the API, the worker and the frontend dev server, plus two one-off
containers: `migrate` (runs on every start) and `tools` (tests and migrations).

**The worker is load-bearing.** Modules announce what happened (a booking confirmed, an invoice
overdue) as events in the database, and the worker delivers them. Without it no customer is
notified, no commission accrues, and an unpaid salon is never hidden from the marketplace.

## How the backend is organised

One folder per business area under `nova_backend/app/modules/`, each with the same set of files
(router, schemas, service, domain, models, repository, events, exceptions, dependencies). Each
module's `__init__.py` says what it owns and what other modules may use.

| Module         | Owns                                                                                       |
| -------------- | ------------------------------------------------------------------------------------------ |
| `identity`     | Tenants (a salon business account), users, staff memberships and roles, customers, consent |
| `catalog`      | Businesses, branches, services and prices, providers, business photos                      |
| `discovery`    | The public marketplace: search, storefronts, referral attribution                          |
| `booking`      | Availability, slot holds, the booking lifecycle (the reference module)                     |
| `queue`        | Walk-in queues, QR tickets, check-in                                                       |
| `review`       | Verified 1–5 ratings of completed visits                                                   |
| `payment`      | Deposits through Moyasar checkout, refunds                                                 |
| `billing`      | What salons pay NOVA: plans, commission, invoices, payouts, dunning                        |
| `analytics`    | Owner reports and charts, read from other modules (owns no tables)                         |
| `notification` | WhatsApp messages, gated on consent and quiet hours                                        |
| `ai_agents`    | Optional assistants for customers and owners; they call services, never the database       |

Every tenant's data is isolated three times over: the URL names the tenant and the caller must
belong to it, every query is filtered by tenant, and PostgreSQL row-level security refuses the
rest. [`nova_backend/README.md`](nova_backend/README.md) explains the rules; ADR-0003 explains why.

## Everyday commands

Run from the repository root. `make help` lists them all.

| Command                   | What it does                                                                                       |
| ------------------------- | -------------------------------------------------------------------------------------------------- |
| `make dev`                | Start the whole stack (migrations run first)                                                       |
| `make down`               | Stop it                                                                                            |
| `make test`               | Run the backend test suite in a container, against its own database                                |
| `make check`              | Lint, type-check, and check the app assembles (needs [uv](https://docs.astral.sh/uv/) on the host) |
| `make revision m="add_x"` | Generate a migration from model changes. Read it before you keep it                                |
| `make migrate`            | Apply migrations again                                                                             |

Frontend checks run from `nova-frontend/`; see [its README](nova-frontend/README.md).

## Optional integrations

The app starts and runs without any of these. Until you configure one, payments and WhatsApp
answer `503 integration_not_configured`, and the assistants hand off to a person.

- **Payments (Moyasar).** Keys, webhook and test cards: [`nova_backend/README.md`, "Payments"](nova_backend/README.md#payments-moyasar).
- **WhatsApp** through a business solution provider: the `WHATSAPP_*` settings in `infra/.env`.
- **AI agents** on a model server on your machine (LM Studio or Ollama): [`nova_backend/README.md`, "AI agents"](nova_backend/README.md#ai-agents-local-models).
- **Public access** through a Cloudflare tunnel, with no open ports: set `CLOUDFLARE_TUNNEL_TOKEN`
  and run `make tunnel`.

## Where to go next

- **New to the code?** Start with [docs/12, the backend code walkthrough](docs/12-Backend-Code-Walkthrough.md):
  one request traced through every file, then an endpoint you add yourself.
- **Working on the frontend?** [nova-frontend/README.md](nova-frontend/README.md).
- **Looking for a design decision?** [docs/decisions/](docs/decisions/) has the ADRs, and
  [docs/00-Index.md](docs/00-Index.md) maps every document.
- **Calling the API?** `/docs` explains sign-in, tenants and conventions, and
  [docs/15](docs/15-API-Error-Codes.md) lists every error code and what to do about it.
- **Security?** [docs/14, the threat model](docs/14-Threat-Model.md).
- **Using an AI coding assistant?** [CLAUDE.md](CLAUDE.md) holds the conventions and gotchas it
  should follow, and is a dense reference for people too.
