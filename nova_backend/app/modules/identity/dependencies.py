from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session, get_tenant_context
from app.core.rate_limit import get_rate_limiter
from app.core.security import Principal, require_staff
from app.modules.identity.auth_service import AuthService
from app.modules.identity.domain import StaffPermission
from app.modules.identity.repository import (
    CustomerRepository,
    MembershipRepository,
    TenantRepository,
    UserRepository,
)
from app.modules.identity.service import CustomerService, MembershipService, TenantService


def get_tenant_repository(
    session: AsyncSession = Depends(get_db_session),
) -> TenantRepository:
    return TenantRepository(session)


def get_membership_repository(
    session: AsyncSession = Depends(get_db_session),
) -> MembershipRepository:
    return MembershipRepository(session)


def get_user_repository(
    session: AsyncSession = Depends(get_db_session),
) -> UserRepository:
    return UserRepository(session)


def get_membership_service(
    memberships: MembershipRepository = Depends(get_membership_repository),
    users: UserRepository = Depends(get_user_repository),
    tenant_id: UUID = Depends(get_tenant_context),
) -> MembershipService:
    """Scoped to the path tenant, which `get_tenant_context` has authorized.

    That dependency also sets the RLS variable for this connection, so the
    `memberships` reads below are bounded by the database as well as by the
    explicit `tenant_id` the service passes into every query.
    """
    return MembershipService(memberships, users=users, tenant_id=tenant_id)


def build_membership_service(session: AsyncSession, tenant_id: UUID) -> MembershipService:
    """Assembles the service outside the request DI graph.

    An AI turn checks the caller's role inside a unit of work of its own, with
    no request session for `get_membership_service` to hang from. The caller
    scopes that session to the tenant first.
    """
    return MembershipService(
        MembershipRepository(session), users=UserRepository(session), tenant_id=tenant_id
    )


class RequirePermission:
    """A route dependency: staff whose role in this tenant carries `permission`.

    Used in place of `require_staff` on the routes that move money or read what
    a business earns, e.g. `Depends(RequirePermission(StaffPermission.
    REFUND_PAYMENTS))`. A customer is refused before any membership is read; a
    member is judged by their active row in `memberships` for the path's tenant,
    never by the token's flattened `roles`.
    """

    def __init__(self, permission: StaffPermission) -> None:
        self.permission = permission

    async def __call__(
        self,
        principal: Principal = Depends(require_staff),
        memberships: MembershipService = Depends(get_membership_service),
    ) -> Principal:
        await memberships.require_permission(principal, self.permission)
        return principal


def get_tenant_service(
    repository: TenantRepository = Depends(get_tenant_repository),
    memberships: MembershipRepository = Depends(get_membership_repository),
) -> TenantService:
    settings = get_settings()
    return TenantService(
        repository,
        memberships=memberships,
        allowed_phone_country_codes=settings.allowed_phone_country_codes,
    )


def build_customer_service(session: AsyncSession, tenant_id: UUID) -> CustomerService:
    """Assembles the service outside the request DI graph.

    Used by the payment webhook and the outbox dispatcher, neither of which has
    an authenticated tenant context to resolve `get_tenant_context` with.
    """
    settings = get_settings()
    return CustomerService(
        CustomerRepository(session, tenant_id),
        tenant_id=tenant_id,
        allowed_phone_country_codes=settings.allowed_phone_country_codes,
        # Arabic, not `settings.default_locale`: that setting is the API's own
        # default, while docs/07 section 6 and docs/08 section 9 both make a GCC
        # customer's default communication language Arabic.
        default_locale="ar",
    )


def get_customer_service(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: UUID = Depends(get_tenant_context),
) -> CustomerService:
    """Tenant-scoped, so one salon's customer list is unreachable from another.

    `tenant_id` comes from the URL path via `get_tenant_context`, which has
    already proven the caller is a member (ADR-0003, ADR-0006).
    """
    return build_customer_service(session, tenant_id)


def get_auth_service(session: AsyncSession = Depends(get_db_session)) -> AuthService:
    """Not tenant-scoped: signing in happens before any tenant is chosen."""
    return AuthService(session, secret_key=get_settings().secret_key, limiter=get_rate_limiter())
