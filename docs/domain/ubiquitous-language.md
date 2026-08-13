# Ubiquitous Language

Terms used consistently across code, docs, and API — see [[glossary|../product/glossary]] for
the short reference version. This page exists to flag terms that are *easy to get wrong*.

- **Tenant**, not "business" or "account", in code and schema names. "Business" is fine in
  product-facing copy.
- **Branch**, not "location" or "outlet" — matches `backend/app/modules/tenants/models.py`.
- **Slug** is always derived, never user-supplied directly — see `generate_slug` in
  [[tenants-and-branches]].
- **Tenant-scoped** describes any repository/query that filters by `tenant_id` by construction
  (can't accidentally omit the filter) — not merely "usually filtered". See
  [[0003-tenant-isolation-strategy|../decisions/0003-tenant-isolation-strategy]].
- **Command** and **Query** are CQRS-lite terms: a command mutates and returns the entity it
  created/changed; a query only reads. Handlers are plain functions
  (`handle_create_tenant`, `handle_get_tenant`), not classes.
