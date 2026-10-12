"""Bounded context: ADMIN — the platform console for NOVA administrators.

Aggregates      AdminAuditEntry
Tables          admin_audit_log
Depends on      identity (superusers; account actions), catalog (listing
                actions), booking (cancellation); every table, read-only,
                through `Base.metadata`
Status          implemented

A Django-admin-style browser over every table, for superusers only
(`users.is_superuser`). It differs from Django's admin on purpose:

  - It reads across tenants. `get_admin_session` opens `bypass_tenant_scope`
    for the request, the third sanctioned request-path bypass after login and
    invite acceptance; see its docstring for what bounds it.
  - It never edits a row directly. Its only writes are the curated actions in
    `domain.ACTIONS`, each run through the owning module's service and scoped
    to the row's tenant, so state machines, events and policies still apply.
  - Credentials are masked in every response (`domain.display_value`): hashes,
    tokens, fingerprints, secrets in JSON payloads; gateway references keep
    their last four characters.
  - Every list, view and action is recorded in `admin_audit_log`, which the
    app role may insert into and read, but not update or delete.

Unlike the other modules it owns no events.

Public surface — what other modules may import: nothing. Nothing depends on it.

Internal — do not import from other modules:
    models.py, repository.py, dependencies.py, router.py, service.py
"""
