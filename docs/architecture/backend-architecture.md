# Backend Architecture

Pragmatic Domain-Driven Design + Vertical Slice Architecture + CQRS-lite. "Pragmatic" is load
bearing: this is not textbook hexagonal architecture — it optimizes for a small team building a
real product quickly, while keeping the seams that matter.

## Vertical slices, not technical layers

Code is grouped by business feature under `backend/app/modules/<name>/`, each owning its own
router, schemas, service/handler, repository, domain rules, models, and events — see
[[module-template|../domain/module-template]] for the exact file list. This is deliberately
*not* a global `routers/`, `models/`, `schemas/` split — changing one feature should mean
touching one directory, not five.

## Domain rules independent of infra

`domain.py` in each module holds pure functions (no SQLAlchemy/FastAPI imports) — see
`backend/app/modules/tenants/domain.py`. `models.py` (SQLAlchemy ORM) doubles as the
data-carrying entity rather than maintaining a separate hexagonal domain-object layer — that
extra indirection isn't justified at this scale. `app/core/exceptions.py` (the `DomainError`
hierarchy) also has zero FastAPI import, so domain/command code can raise these without a web
framework dependency; `app/core/error_handlers.py` is the FastAPI-side translation into HTTP
responses.

## CQRS-lite

Each module has `commands.py` (mutations) and `queries.py` (reads), each a dataclass +
handler function pair. No `service.py` god-class — see [[module-template|../domain/module-template]]
for when adding one is actually justified.

## Repository pattern

`app/db/repository.py` defines `BaseRepository[T]` and `TenantScopedRepository[T]`. Every
module repository extends one of these rather than calling SQLAlchemy directly from
commands/queries — see [[multi-tenancy]] for why `TenantScopedRepository` exists.

## Dependency injection

FastAPI `Depends()` wires sessions → repositories → route handlers
(`app/modules/tenants/dependencies.py`). Routers never construct a session or repository
directly.

## Replaceable integrations

External systems (WhatsApp, Moyasar, Nextcloud) are `Protocol` + placeholder adapter pairs
under `app/integrations/` — see [[../integrations/whatsapp|whatsapp]] etc. Module code depends
on the Protocol, never a concrete SDK client.
