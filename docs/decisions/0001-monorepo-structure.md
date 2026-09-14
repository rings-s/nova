# 0001 — Monorepo Structure

## Status

Accepted, with the layout amended — 2026-08-16. The backend directory is `nova_backend/`, not
`backend/`. The `frontend/` directory is currently absent from the working tree; CI detects this
and skips the frontend jobs rather than failing. The monorepo decision itself stands.

## Context

NOVA needs a backend (FastAPI), frontend (SvelteKit), infra config, and docs. Team is
small/solo at this stage.

## Decision

Single git repository with `/nova_backend`, `/frontend`, `/infra`, `/docs` at the root, rather
than separate repositories per component. (Originally `/backend`; renamed since.)

## Consequences

- One `docker-compose.yml` can reference both `../nova_backend` and `../frontend` build contexts
  directly.
- One PR can span a backend change and its matching frontend/docs change.
- No cross-repo version pinning/release coordination needed yet.

## Alternatives considered

Polyrepo (separate backend/frontend/infra repos) — deferred. Worth revisiting only if separate
deploy pipelines or separate teams make a single repo's CI/PR flow a bottleneck.
