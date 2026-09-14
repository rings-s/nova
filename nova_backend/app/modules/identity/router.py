"""identity · DELIVERY layer — HTTP.

Every route here was previously unauthenticated. `POST /tenants` let anyone
create a business, and `GET /tenants` returned every tenant on the platform with
its phone number — a full customer-list enumeration for a competitor. ADR-0006
claimed all endpoints required a bearer token; these were the exception.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_tenant_context
from app.core.pagination import PageParams
from app.core.schemas import Page
from app.core.security import Principal, PrincipalKind, get_principal, require_staff
from app.core.throttling import write_rate_limit
from app.modules.identity.dependencies import (
    get_customer_service,
    get_membership_service,
    get_tenant_service,
)
from app.modules.identity.models import Customer, Membership, Tenant
from app.modules.identity.schemas import (
    CustomerCreate,
    CustomerRead,
    CustomerUpdateConsent,
    MembershipCreate,
    MembershipRead,
    MembershipUpdateRole,
    TenantCreate,
    TenantRead,
)
from app.modules.identity.service import CustomerService, MembershipService, TenantService

router = APIRouter(prefix="/tenants", tags=["identity"])


@router.post(
    "",
    response_model=TenantRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(write_rate_limit)],
)
async def create_tenant(
    payload: TenantCreate,
    session: AsyncSession = Depends(get_db_session),
    service: TenantService = Depends(get_tenant_service),
    principal: Principal = Depends(get_principal),
) -> Tenant:
    """Registers a business. The caller becomes its owner.

    Any authenticated account may do this — that is the self-serve signup path.
    The membership row is what grants access afterwards, so the caller must
    refresh their token before they can use the tenant-scoped endpoints.
    """
    # A service principal has no `users` row to own the tenant with, and is not
    # tenant-scoped anyway; a human caller always becomes the owner.
    owner_user_id = None if principal.kind is PrincipalKind.SERVICE else principal.subject_id

    tenant = await service.create(**payload.model_dump(), owner_user_id=owner_user_id)
    await session.commit()
    return tenant


@router.get("", response_model=Page[TenantRead])
async def list_my_tenants(
    params: PageParams = Depends(),
    service: TenantService = Depends(get_tenant_service),
    principal: Principal = Depends(get_principal),
) -> Page[TenantRead]:
    """The caller's own businesses, never the whole platform's."""
    tenants = await service.list_for_principal(principal, limit=params.limit, offset=params.offset)
    return Page(items=[TenantRead.model_validate(t) for t in tenants])


@router.get("/{tenant_id}", response_model=TenantRead)
async def get_tenant(
    tenant_id: UUID = Depends(get_tenant_context),
    service: TenantService = Depends(get_tenant_service),
) -> Tenant:
    """`get_tenant_context` proves membership before the id is used at all."""
    return await service.get(tenant_id)


# --- Customers ------------------------------------------------------------
#
# Staff-only. A customer principal has no business reading a salon's customer
# list, and `require_staff` is what stops a signed-in customer walking the
# whole book by hand.

customers_router = APIRouter(prefix="/tenants/{tenant_id}/customers", tags=["identity"])


@customers_router.post(
    "",
    response_model=CustomerRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def create_customer(
    tenant_id: UUID,
    payload: CustomerCreate,
    session: AsyncSession = Depends(get_db_session),
    service: CustomerService = Depends(get_customer_service),
) -> Customer:
    customer = await service.create(**payload.model_dump())
    await session.commit()
    return customer


@customers_router.get("", response_model=Page[CustomerRead], dependencies=[Depends(require_staff)])
async def list_customers(
    tenant_id: UUID,
    q: str | None = Query(default=None, description="Partial name or phone."),
    params: PageParams = Depends(),
    service: CustomerService = Depends(get_customer_service),
) -> Page[CustomerRead]:
    rows = (
        await service.search(q, limit=params.limit, offset=params.offset)
        if q
        else await service.list(limit=params.limit, offset=params.offset)
    )
    return Page(items=[CustomerRead.model_validate(r) for r in rows])


@customers_router.get(
    "/{customer_id}", response_model=CustomerRead, dependencies=[Depends(require_staff)]
)
async def get_customer(
    tenant_id: UUID,
    customer_id: UUID,
    service: CustomerService = Depends(get_customer_service),
) -> Customer:
    return await service.get(customer_id)


@customers_router.patch(
    "/{customer_id}/consent",
    response_model=CustomerRead,
    dependencies=[Depends(require_staff)],
)
async def update_customer_consent(
    tenant_id: UUID,
    customer_id: UUID,
    payload: CustomerUpdateConsent,
    session: AsyncSession = Depends(get_db_session),
    service: CustomerService = Depends(get_customer_service),
) -> Customer:
    """PDPL: withdrawing consent must be as easy as giving it."""
    customer = await service.update_consent(customer_id, **payload.model_dump())
    await session.commit()
    return customer


# --- Memberships ----------------------------------------------------------
#
# Who works at a salon, per docs/03 section 1. Until this existed the only
# `Membership` row anyone could create was the OWNER written inline when the
# tenant was registered, so a business had exactly one user forever — which
# made the "unlimited staff seats" of docs/11 section 2 unsellable.
#
# `require_staff` is the outer gate and does not decide anything on its own: it
# only refuses customer principals, who now reach every tenant by design. Rank
# is settled inside `MembershipService` against this tenant's `memberships`
# row, because the token's flat `roles` claim spans every salon the caller
# belongs to and cannot answer a per-tenant question.

memberships_router = APIRouter(prefix="/tenants/{tenant_id}/memberships", tags=["identity"])


def _membership_read(membership: Membership) -> MembershipRead:
    return MembershipRead(
        id=membership.id,
        tenant_id=membership.tenant_id,
        user_id=membership.user_id,
        email=membership.user.email,
        full_name=membership.user.full_name,
        role=membership.role,
        is_active=membership.is_active,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


@memberships_router.get(
    "", response_model=Page[MembershipRead], dependencies=[Depends(require_staff)]
)
async def list_memberships(
    tenant_id: UUID,
    params: PageParams = Depends(),
    service: MembershipService = Depends(get_membership_service),
    principal: Principal = Depends(get_principal),
) -> Page[MembershipRead]:
    """This salon's staff, active only. Revoked memberships are history."""
    rows = await service.list(principal, limit=params.limit, offset=params.offset)
    return Page(items=[_membership_read(r) for r in rows])


@memberships_router.post(
    "",
    response_model=MembershipRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def grant_membership(
    tenant_id: UUID,
    payload: MembershipCreate,
    session: AsyncSession = Depends(get_db_session),
    service: MembershipService = Depends(get_membership_service),
    principal: Principal = Depends(get_principal),
) -> MembershipRead:
    """Adds an existing NOVA account to this business.

    404 on an unknown address: there is no invite flow yet, so the person must
    already have registered. 409 if they already work here — changing somebody
    already on staff is `PATCH`, so a mistyped role cannot silently demote a
    colleague.

    The grantee's current access token does not carry this tenant; they pick it
    up on their next `/auth/refresh`, within the 15-minute access token life.
    """
    membership = await service.grant(principal, email=payload.email, role=payload.role)
    await session.commit()
    return _membership_read(membership)


@memberships_router.patch(
    "/{membership_id}",
    response_model=MembershipRead,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def change_membership_role(
    tenant_id: UUID,
    membership_id: UUID,
    payload: MembershipUpdateRole,
    session: AsyncSession = Depends(get_db_session),
    service: MembershipService = Depends(get_membership_service),
    principal: Principal = Depends(get_principal),
) -> MembershipRead:
    """409 when it would leave the business with no owner."""
    membership = await service.change_role(
        principal, membership_id=membership_id, role=payload.role
    )
    await session.commit()
    return _membership_read(membership)


@memberships_router.delete(
    "/{membership_id}",
    response_model=MembershipRead,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def revoke_membership(
    tenant_id: UUID,
    membership_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: MembershipService = Depends(get_membership_service),
    principal: Principal = Depends(get_principal),
) -> MembershipRead:
    """Withdraws access, keeping the row.

    Returns the revoked membership rather than 204 so the caller can see the
    state it landed in. The last active owner cannot be removed — 409 — or the
    business becomes unadministrable with no way back.
    """
    membership = await service.revoke(principal, membership_id=membership_id)
    await session.commit()
    return _membership_read(membership)
