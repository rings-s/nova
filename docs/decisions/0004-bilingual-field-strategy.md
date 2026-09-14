# 0004 — Bilingual Field Strategy

## Context

NOVA requires Arabic and English support. Tenant/branch names need both languages, and future
modules (services, categories) will likely need the same bilingual pattern.

## Decision

`name_en` / `name_ar` columns directly on the entity (e.g. `Tenant.name_en`, `Tenant.name_ar`),
not a separate translations table. Both are required at creation — enforced by
`require_bilingual_text` in `nova_backend/app/core/validators.py` (moved there from the old
`tenants/domain.py` once `catalog` needed the same rule — the reuse this ADR anticipated).

## Consequences

- Simple reads: no join required to render a tenant/branch name.
- Locale count is fixed at 2 in the schema — adding a third locale means a migration touching
  every bilingual table, not a data-only change.
- Pattern is copy-pasteable: any future module needing the same two-locale requirement can
  reuse `require_bilingual_text` and the `name_en`/`name_ar` column-pair convention.

## Alternatives considered

**Translations table** (`entity_id, locale, field, value`) — rejected for now: buys N-locale
flexibility at the cost of a join on every read and more migration complexity. Not justified
while only `en`/`ar` are in scope (YAGNI).

**JSONB `i18n` column** (`{"en": "...", "ar": "..."}`) — noted as the next escalation, cheaper
than a translations table, still flexible on locale count. Reach for this before a full
translations table if a module needs longer free text in more than two locales (e.g. service
descriptions, once healthcare/auto verticals are added).
