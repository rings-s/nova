# Module Template

How to build the next vertical-slice module, using `backend/app/modules/tenants/` as the
reference. See [[backend-architecture|../architecture/backend-architecture]] for the
architectural rationale.

## Checklist

1. Create `backend/app/modules/<name>/` with:
   - `models.py` — SQLAlchemy ORM classes. Use `TenantOwnedMixin` (from `app/db/mixins.py`) if
     the entity belongs to a tenant.
   - `domain.py` — pure functions for validation/business rules. No SQLAlchemy/FastAPI imports.
   - `exceptions.py` — subclasses of `NotFoundError`/`ConflictError`/`ValidationDomainError`
     (from `app/core/exceptions.py`).
   - `schemas.py` — Pydantic v2 request/response models.
   - `repository.py` — extend `BaseRepository`/`TenantScopedRepository` (from
     `app/db/repository.py`).
   - `commands.py` / `queries.py` — CQRS-lite: dataclasses + handler functions. No
     `service.py` god-class — see [[backend-architecture]] for when that changes.
   - `events.py` — domain event dataclasses, even if nothing dispatches them yet.
   - `dependencies.py` — FastAPI DI providers for the module's repositories.
   - `router.py` — FastAPI `APIRouter`, business logic stays in commands/queries, not here.
   - `ai/__init__.py` — reserved for future PydanticAI tool bindings scoped to this module.
2. Add the module's models import and router to `backend/app/modules/registry.py`.
3. Generate a migration: `uv run alembic revision --autogenerate -m "..."`, review it by hand.
4. Add tests under `backend/tests/modules/<name>/`: `test_domain.py` (pure, no DB),
   `test_repository.py` (isolation/persistence), `test_router.py` (end-to-end via
   `httpx.AsyncClient`) — see `backend/tests/conftest.py` for fixtures.
5. Document the module: one file under `docs/domain/`, one under `docs/api/` if it exposes
   endpoints, and an ADR under `docs/decisions/` for any non-obvious choice.

## When to deviate

- Add `service.py` only when a command/query handler needs to orchestrate logic shared across
  multiple commands — not preemptively.
- Add a translations table instead of `name_en`/`name_ar` columns only if a module needs more
  than two locales or long free text — see
  [[0004-bilingual-field-strategy|../decisions/0004-bilingual-field-strategy]].
