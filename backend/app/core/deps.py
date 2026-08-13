from uuid import UUID

from fastapi import Path

from app.db.session import get_db_session

__all__ = ["get_db_session", "get_tenant_context"]


async def get_tenant_context(tenant_id: UUID = Path(...)) -> UUID:
    """Resolves the active tenant strictly from the URL path.

    Used to build tenant-scoped repositories (see TenantScopedRepository) so a
    request can never influence its own tenant scope via body or query params.
    """
    return tenant_id
