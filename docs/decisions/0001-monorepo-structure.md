# 0001 — Monorepo Structure

## Context

NOVA needs a backend (FastAPI), frontend (SvelteKit), infra config, and docs. Team is
small/solo at this stage.

## Decision

Single git repository with `/backend`, `/frontend`, `/infra`, `/docs` at the root, rather than
separate repositories per component.

## Consequences

- One `docker-compose.yml` can reference both `../backend` and `../frontend` build contexts
  directly.
- One PR can span a backend change and its matching frontend/docs change.
- No cross-repo version pinning/release coordination needed yet.

## Alternatives considered

Polyrepo (separate backend/frontend/infra repos) — deferred. Worth revisiting only if separate
deploy pipelines or separate teams make a single repo's CI/PR flow a bottleneck.
