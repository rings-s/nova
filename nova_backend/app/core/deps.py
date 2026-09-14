"""Shared FastAPI dependencies.

`get_tenant_context` used to return the path's `tenant_id` with no verification
that the caller was entitled to it. It now delegates to
`security.require_tenant_access`, which authenticates the request and checks
tenant membership before the value is used to scope a repository.

The name is kept so module `dependencies.py` files did not all have to change,
and because "tenant context" is still what it produces — it is simply an
authorized one now.
"""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import set_principal_id, set_tenant_id
from app.core.security import Principal, get_principal, require_tenant_access
from app.db.session import get_db_session, set_tenant_scope

__all__ = [
    "Principal",
    "get_authorized_tenant",
    "get_db_session",
    "get_principal",
    "get_tenant_context",
]


async def get_authorized_tenant(
    tenant_id: UUID = Depends(require_tenant_access),
    principal: Principal = Depends(get_principal),
) -> UUID:
    """The authorized tenant, without opening a transaction.

    `require_tenant_access` has already proven the caller may act on this
    tenant (401/403 otherwise). The request context is stamped here, so every
    later log line carries tenant and principal without any call site passing
    them along.

    Only a route that holds no request transaction depends on this directly —
    the AI chat, whose units of work each scope their own connection. Every
    other tenant route wants `get_tenant_context`.
    """
    set_tenant_id(tenant_id)
    set_principal_id(principal.subject_id)
    return tenant_id


async def get_tenant_context(
    tenant_id: UUID = Depends(get_authorized_tenant),
    session: AsyncSession = Depends(get_db_session),
) -> UUID:
    """The authorized tenant for this request, with its connection scoped for RLS.

    Postgres itself then refuses cross-tenant rows even if application code
    slips. The scope is `SET LOCAL`, so it lasts exactly as long as the
    transaction the router commits.
    """
    await set_tenant_scope(session, tenant_id)
    return tenant_id
