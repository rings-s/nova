"""admin · wiring.

`get_admin_session` is where the console crosses tenants, and the only place:
it opens `bypass_tenant_scope` after `require_superuser` has passed, for this
request's transaction alone (`SET LOCAL`).
"""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.security import Principal
from app.db.session import bypass_tenant_scope
from app.modules.admin.repository import AdminAuditRepository, AdminTableRepository
from app.modules.admin.service import AdminService
from app.modules.booking.dependencies import build_booking_service
from app.modules.booking.service import BookingService
from app.modules.catalog.dependencies import build_catalog_service
from app.modules.catalog.service import CatalogService
from app.modules.identity.auth_service import AuthService
from app.modules.identity.dependencies import get_auth_service, require_superuser


async def get_admin_session(
    principal: Principal = Depends(require_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> AsyncSession:
    """The request's session, reading across tenants.

    The third sanctioned request-path bypass (CLAUDE.md, docs/14). Unlike login
    and invite acceptance, it is not closed before the handler runs: reading
    every tenant is the console's purpose. What bounds it instead:

      - only a superuser reaches it, re-read from the account row each request;
      - the console reads through `AdminTableRepository` and writes nothing
        generic: each curated action re-scopes to the row's own tenant first
        (`AdminService._scoped`), which also switches the bypass off;
      - every read and action is recorded in `admin_audit_log`, which the app
        role cannot update or delete.
    """
    await bypass_tenant_scope(session)
    return session


def get_admin_service(
    session: AsyncSession = Depends(get_admin_session),
    auth: AuthService = Depends(get_auth_service),
) -> AdminService:
    def catalog_for(tenant_id: UUID) -> CatalogService:
        return build_catalog_service(session, tenant_id)

    def bookings_for(tenant_id: UUID) -> BookingService:
        return build_booking_service(session, tenant_id)

    return AdminService(
        session=session,
        tables=AdminTableRepository(session),
        audit=AdminAuditRepository(session),
        auth=auth,
        catalog_for=catalog_for,
        bookings_for=bookings_for,
    )
