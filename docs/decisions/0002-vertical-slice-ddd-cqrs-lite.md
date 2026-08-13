# 0002 — Vertical Slice Architecture + Pragmatic DDD + CQRS-lite

## Context

NOVA will grow many business modules (tenants, booking, queue, payments, WhatsApp, AI
support/sales/retention...). A layered architecture (`routers/`, `models/`, `schemas/` at the
top level) tends to make each new feature touch many directories and makes module boundaries
implicit.

## Decision

Group backend code by business feature under `backend/app/modules/<name>/`, each owning its
router, schemas, service/handler, repository, domain rules, models, and events. Within a
module, use CQRS-lite: `commands.py`/`queries.py` as dataclass + handler-function pairs, no
`service.py` god-class by default. Domain rules (`domain.py`) are pure functions with no
FastAPI/SQLAlchemy imports.

## Consequences

- Adding a module (see [[../domain/module-template]]) means creating one directory, not
  editing five existing ones.
- Domain rules are unit-testable without a database or HTTP layer.
- No service layer to prematurely design — added only when a module's commands need shared
  orchestration.

## Alternatives considered

Classic layered architecture (routers/models/schemas at top level) — rejected: doesn't scale
to many modules without constant cross-directory changes per feature.

Full hexagonal architecture with separate domain entities distinct from ORM models — rejected
for now: the extra object-mapping layer isn't justified at this scale; `models.py` doubles as
the domain entity. Revisit if a module's domain logic outgrows what's comfortable to express
directly on the ORM class.
