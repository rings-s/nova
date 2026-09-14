# 0002 — Vertical Slice Architecture + Pragmatic DDD + CQRS-lite

> [!warning] Partially superseded — 2026-08-15
> Two parts of this ADR no longer describe the code:
>
> 1. **CQRS-lite is out.** Modules use `service.py`, not `commands.py`/`queries.py`, to match
>    docs 02/06/07 and the README. The handler-pair style was implemented in the old `tenants`
>    module and collapsed into `TenantService` when that module became `identity`.
> 2. **Rich domain entities are in, selectively.** This ADR rejected domain entities distinct
>    from ORM models outright. That still holds for `identity`, `catalog`, `media`, and
>    `notification` — but `booking`, `queue`, and `payment` own real state machines and define
>    their own entities in `domain.py`, with the repository mapping to the ORM row. See
>    `nova_backend/README.md`, "Two styles of domain.py", for the test used to decide.
>
> **Still in force:** the vertical-slice layout itself, one directory per bounded context, and
> the rule that `domain.py` has no FastAPI or SQLAlchemy imports.
>
> Paths below say `backend/app/...`; the tree is now `nova_backend/app/...`.

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
