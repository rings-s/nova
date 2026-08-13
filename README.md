# NOVA

GCC-focused AI booking and customer-operations platform. Initial vertical: beauty centers,
salons, spas, massage centers, and wellness businesses. Connects Customer ↔ Business ↔ Service
Provider for discovery, booking, payments, virtual QR tickets, walk-in queues, WhatsApp
communication, and AI-assisted support/sales/retention.

> Proprietary software. See `LICENSE`.

## Layout

- `backend/` — FastAPI + Pydantic v2 + SQLAlchemy 2.0 async, vertical-slice modules under `app/modules/`
- `frontend/` — SvelteKit + Svelte 5 + TypeScript PWA
- `infra/` — Docker Compose stack and environment templates
- `docs/` — Obsidian-friendly documentation vault (product, domain, architecture, API, AI, frontend, integrations, operations, decisions, legal)

## Status

Initial scaffold. One working vertical slice — `tenants` (business + branch registration,
[docs](docs/domain/tenants-and-branches.md)) — is the reference pattern for every module that
follows (see [docs/domain/module-template.md](docs/domain/module-template.md)). Booking,
queues, payments, WhatsApp, and AI are not built yet; their integration points are stubbed as
replaceable adapters — see [docs/integrations/](docs/integrations/).

## Quick start

See [`docs/operations/local-dev-setup.md`](docs/operations/local-dev-setup.md).

```
make dev      # bring up postgres, redis, backend, worker, frontend via Docker Compose
make migrate  # apply Alembic migrations
make test     # run backend test suite
```

`docker compose up` has not been run in the environment this scaffold was built in (no
docker-group access there) — verify it in your real environment. Backend and frontend were
each verified directly (uv/pnpm) instead; see `docs/operations/local-dev-setup.md` Option B.
