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
    get_membership_service_unauthorized,
    get_tenant_service,
)
from app.modules.identity.models import Customer, Membership, MembershipInvite, Tenant
from app.modules.identity.schemas import (
    AcceptInviteRequest,
    CreateCustomerRequest,
    CreateMembershipRequest,
    CreateTenantRequest,
    CustomerOut,
    MembershipInviteOut,
    MembershipInviteSummary,
    MembershipOut,
    MyAccessOut,
    TenantOut,
    UpdateCustomerConsentRequest,
    UpdateMembershipRoleRequest,
)
from app.modules.identity.service import CustomerService, MembershipService, TenantService

router = APIRouter(prefix="/tenants", tags=["identity"])


@router.post(
    "",
    response_model=TenantOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(write_rate_limit)],
)
async def create_tenant(
    payload: CreateTenantRequest,
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


@router.get("", response_model=Page[TenantOut])
async def list_my_tenants(
    params: PageParams = Depends(),
    service: TenantService = Depends(get_tenant_service),
    principal: Principal = Depends(get_principal),
) -> Page[TenantOut]:
    """The caller's own businesses, never the whole platform's."""
    tenants = await service.list_for_principal(principal, limit=params.limit, offset=params.offset)
    return Page(items=[TenantOut.model_validate(t) for t in tenants])


@router.get("/{tenant_id}", response_model=TenantOut)
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
    response_model=CustomerOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def create_customer(
    tenant_id: UUID,
    payload: CreateCustomerRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CustomerService = Depends(get_customer_service),
) -> Customer:
    customer = await service.create(**payload.model_dump())
    await session.commit()
    return customer


@customers_router.get("", response_model=Page[CustomerOut], dependencies=[Depends(require_staff)])
async def list_customers(
    tenant_id: UUID,
    q: str | None = Query(default=None, description="Partial name or phone."),
    params: PageParams = Depends(),
    service: CustomerService = Depends(get_customer_service),
) -> Page[CustomerOut]:
    rows = (
        await service.search(q, limit=params.limit, offset=params.offset)
        if q
        else await service.list(limit=params.limit, offset=params.offset)
    )
    return Page(items=[CustomerOut.model_validate(r) for r in rows])


@customers_router.get(
    "/{customer_id}", response_model=CustomerOut, dependencies=[Depends(require_staff)]
)
async def get_customer(
    tenant_id: UUID,
    customer_id: UUID,
    service: CustomerService = Depends(get_customer_service),
) -> Customer:
    return await service.get(customer_id)


@customers_router.patch(
    "/{customer_id}/consent",
    response_model=CustomerOut,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def update_customer_consent(
    tenant_id: UUID,
    customer_id: UUID,
    payload: UpdateCustomerConsentRequest,
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


def _membership_out(membership: Membership) -> MembershipOut:
    return MembershipOut(
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
    "", response_model=Page[MembershipOut], dependencies=[Depends(require_staff)]
)
async def list_memberships(
    tenant_id: UUID,
    params: PageParams = Depends(),
    service: MembershipService = Depends(get_membership_service),
    principal: Principal = Depends(get_principal),
) -> Page[MembershipOut]:
    """This salon's staff, active only. Revoked memberships are history."""
    rows = await service.list(principal, limit=params.limit, offset=params.offset)
    return Page(items=[_membership_out(r) for r in rows])


@memberships_router.get("/me", response_model=MyAccessOut, dependencies=[Depends(require_staff)])
async def get_my_access(
    tenant_id: UUID,
    service: MembershipService = Depends(get_membership_service),
    principal: Principal = Depends(get_principal),
) -> MyAccessOut:
    """Your role in this business and what it unlocks — so a client can show
    only the screens you can use. Every other route still checks for itself."""
    role, permissions, manageable = await service.my_access(principal)
    return MyAccessOut(
        role=role,
        permissions=sorted(permissions),
        manageable_roles=sorted(manageable),
    )


def _invite_out(invite: MembershipInvite, token: str) -> MembershipInviteOut:
    return MembershipInviteOut(
        id=invite.id,
        tenant_id=invite.tenant_id,
        email=invite.email,
        role=invite.role,
        token=token,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
    )


@memberships_router.post(
    "",
    response_model=MembershipInviteOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def invite_membership(
    tenant_id: UUID,
    payload: CreateMembershipRequest,
    session: AsyncSession = Depends(get_db_session),
    service: MembershipService = Depends(get_membership_service),
    principal: Principal = Depends(get_principal),
) -> MembershipInviteOut:
    """Starts staff access for `email`. Nobody has it yet.

    The response's `token` is shown once, here, and is the entire credential
    for accepting the invite (`POST .../invites/{id}/accept`) — relaying it to
    the actual person is the caller's job, by whatever means they would use
    anyway. NOVA never resolves this by matching `email` against an existing
    account (docs/14 TM-04): whoever registered that address first no longer
    matters, only whoever holds the token does.
    """
    invite, token = await service.invite(principal, email=payload.email, role=payload.role)
    await session.commit()
    return _invite_out(invite, token)


@memberships_router.get(
    "/invites",
    response_model=Page[MembershipInviteSummary],
    dependencies=[Depends(require_staff)],
)
async def list_pending_invites(
    tenant_id: UUID,
    params: PageParams = Depends(),
    service: MembershipService = Depends(get_membership_service),
    principal: Principal = Depends(get_principal),
) -> Page[MembershipInviteSummary]:
    """Invites this business has sent that nobody has redeemed yet.

    Never includes a token — those are shown exactly once, at creation.
    """
    rows = await service.list_invites(principal, limit=params.limit, offset=params.offset)
    return Page(items=[MembershipInviteSummary.model_validate(r) for r in rows])


@memberships_router.post(
    "/invites/{invite_id}/accept",
    response_model=MembershipOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(write_rate_limit)],
)
async def accept_membership_invite(
    tenant_id: UUID,
    invite_id: UUID,
    payload: AcceptInviteRequest,
    session: AsyncSession = Depends(get_db_session),
    service: MembershipService = Depends(get_membership_service_unauthorized),
    principal: Principal = Depends(get_principal),
) -> MembershipOut:
    """Redeems an invite token. The token is the entire credential.

    Deliberately reachable by a principal with no existing tie to this
    tenant — see `get_membership_service_unauthorized` and
    `SELF_AUTHORIZING_TENANT_ROUTES` in `tests/test_route_guards.py`. Any
    authenticated account may call this; whether the token checks out is
    where the actual authorization happens.
    """
    membership = await service.accept_invite(principal, invite_id=invite_id, token=payload.token)
    await session.commit()
    return _membership_out(membership)


@memberships_router.patch(
    "/{membership_id}",
    response_model=MembershipOut,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def change_membership_role(
    tenant_id: UUID,
    membership_id: UUID,
    payload: UpdateMembershipRoleRequest,
    session: AsyncSession = Depends(get_db_session),
    service: MembershipService = Depends(get_membership_service),
    principal: Principal = Depends(get_principal),
) -> MembershipOut:
    """409 when it would leave the business with no owner."""
    membership = await service.change_role(
        principal, membership_id=membership_id, role=payload.role
    )
    await session.commit()
    return _membership_out(membership)


@memberships_router.delete(
    "/{membership_id}",
    response_model=MembershipOut,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def revoke_membership(
    tenant_id: UUID,
    membership_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: MembershipService = Depends(get_membership_service),
    principal: Principal = Depends(get_principal),
) -> MembershipOut:
    """Withdraws access, keeping the row.

    Returns the revoked membership rather than 204 so the caller can see the
    state it landed in. The last active owner cannot be removed — 409 — or the
    business becomes unadministrable with no way back.
    """
    membership = await service.revoke(principal, membership_id=membership_id)
    await session.commit()
    return _membership_out(membership)
