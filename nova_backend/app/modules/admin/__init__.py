"""Bounded context: ADMIN — the platform console for NOVA administrators.

Aggregates      AdminAuditEntry
Tables          admin_audit_log
Depends on      identity (superusers; account actions), catalog (listing
                actions), booking (cancellation); every table through
                `Base.metadata`
Status          implemented

A Django-admin-style console over every table, for superusers only
(`users.is_superuser`):

  - It reads across tenants. `get_admin_session` opens `bypass_tenant_scope`
    for the request, the third sanctioned request-path bypass after login and
    invite acceptance; see its docstring for what bounds it.
  - It writes two ways. The curated actions in `domain.ACTIONS` run through
    the owning module's service, so state machines, events and policies still
    apply. Direct edits add, change or delete any row of any table but the
    audit log (`domain.READ_ONLY_TABLES`), as plain SQL: only the database's
    constraints apply. Both are scoped to the row's tenant before writing. A
    superuser can't delete, deactivate or un-superuser their own account.
  - Credentials are masked in every response (`domain.display_value`): hashes,
    tokens, fingerprints, secrets in JSON payloads; gateway references keep
    their last four characters.
  - Every list, view, action and direct edit is recorded in `admin_audit_log`
    (an edit with its values before and after, masked), which the app role may
    insert into and read, but not update or delete.

Unlike the other modules it owns no events.

Public surface — what other modules may import: nothing. Nothing depends on it.

Internal — do not import from other modules:
    models.py, repository.py, dependencies.py, router.py, service.py
"""
