"""Money routes and owner agents, by the caller's role in the salon. Needs Postgres.

`require_staff` answers "does this person work at a salon on NOVA". These
answer "may this person, in this salon, do this": read from the tenant's
`memberships` row, never from the token's `roles`, which is flattened across
every salon a user works at. The policy itself is pinned without a database in
tests/modules/identity/test_domain.py; this checks every gate enforces it.
"""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, PrincipalKind, get_principal
from app.modules.ai_agents.dependencies import get_inference_engine
from app.modules.ai_agents.runtime import InferenceEngine
from app.modules.identity.domain import MembershipRole, StaffPermission, role_allows
from app.modules.identity.models import Membership, User

_MANAGE = {StaffPermission.MANAGE_SUBSCRIPTION}
_REFUND = {StaffPermission.REFUND_PAYMENTS}
_FINANCIALS = {StaffPermission.VIEW_FINANCIALS}
_INSIGHTS = {StaffPermission.VIEW_ANALYTICS}

#: A request that reaches each gate, and the permissions it needs. Bodies are
#: minimal: a caller let through may still get a 404 or a 422, and only an
#: `insufficient_role` 403 means the gate refused.
GATED = [
    ("POST", "billing/subscriptions", _MANAGE),
    ("POST", "billing/subscriptions/{business_id}/plan", _MANAGE),
    ("POST", "billing/subscriptions/{business_id}/cancel", _MANAGE),
    ("GET", "billing/subscriptions/{business_id}", _FINANCIALS),
    ("GET", "billing/invoices?business_id={business_id}", _FINANCIALS),
    ("GET", "billing/invoices/{stranger}", _FINANCIALS),
    ("GET", "billing/invoices/{stranger}/lines", _FINANCIALS),
    ("GET", "billing/commission-lines/{stranger}/explain", _FINANCIALS),
    ("GET", "billing/payouts?business_id={business_id}", _FINANCIALS),
    ("POST", "payments/{stranger}/refund", _REFUND),
    ("GET", "analytics/overview?business_id={business_id}", _INSIGHTS),
    ("GET", "analytics/financial-summary?business_id={business_id}", _INSIGHTS | _FINANCIALS),
]


@pytest.fixture
async def salon(tenant_factory, business_factory):
    tenant = await tenant_factory()
    return tenant, await business_factory(tenant)


async def _staff(
    db_session: AsyncSession, as_owner, tenant, role: MembershipRole | None
) -> Principal:
    """A staff token naming this tenant, whose holder has `role` here (None: no row)."""
    user = User(
        email=f"staff-{uuid4().hex[:8]}@example.com",
        full_name="Staff Member",
        password_hash="not-a-real-hash",
    )
    db_session.add(user)
    await db_session.flush()
    if role is not None:
        async with as_owner():
            db_session.add(Membership(user_id=user.id, tenant_id=tenant.id, role=role))
            await db_session.flush()
    return Principal(
        subject_id=user.id, kind=PrincipalKind.STAFF, tenant_ids=frozenset({tenant.id})
    )


def _refused(response) -> bool:
    return response.status_code == 403 and response.json()["error"]["code"] == "insufficient_role"


@pytest.mark.parametrize("role", list(MembershipRole))
async def test_each_money_route_admits_exactly_the_roles_holding_its_permissions(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, as_owner, salon, role
):
    tenant, business = salon
    principal = await _staff(db_session, as_owner, tenant, role)
    app.dependency_overrides[get_principal] = lambda: principal

    mismatched = []
    for method, template, permissions in GATED:
        path = template.format(business_id=business.id, stranger=uuid4())
        response = await client.request(
            method,
            f"/api/v1/tenants/{tenant.id}/{path}",
            json={} if method == "POST" else None,
        )
        allowed = all(role_allows(role, permission) for permission in permissions)
        if allowed == _refused(response):
            mismatched.append(f"{method} {path} -> {response.status_code}")

    assert mismatched == []


async def test_a_staff_token_with_no_membership_here_is_refused(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, as_owner, salon
):
    """A staff token naming a salon its holder has no role at.

    A revoked member's own token no longer gets this far, since revoking bumps
    their `token_version`. The gate must hold without relying on that.
    """
    tenant, _ = salon
    principal = await _staff(db_session, as_owner, tenant, None)
    app.dependency_overrides[get_principal] = lambda: principal

    response = await client.post(f"/api/v1/tenants/{tenant.id}/payments/{uuid4()}/refund", json={})

    assert _refused(response)


async def test_a_customer_is_refused_before_any_membership_is_read(
    app: FastAPI, client: AsyncClient, salon
):
    tenant, _ = salon
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=uuid4(), kind=PrincipalKind.CUSTOMER
    )

    response = await client.post(f"/api/v1/tenants/{tenant.id}/payments/{uuid4()}/refund", json={})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def _engine_off(app: FastAPI) -> None:
    app.dependency_overrides[get_inference_engine] = lambda: InferenceEngine(
        base_url="http://unused.invalid/v1",
        routing_model="routing",
        reasoning_model="reasoning",
        enabled=False,
    )


async def _ask(client: AsyncClient, tenant, business, agent: str):
    return await client.post(
        f"/api/v1/tenants/{tenant.id}/ai/chat",
        params={"agent": agent},
        json={
            "session_id": "role-test",
            "message": "How did we do?",
            "business_id": str(business.id),
        },
    )


@pytest.mark.parametrize(
    ("role", "agent"),
    [
        (MembershipRole.RECEPTIONIST, "accountant_agent"),
        (MembershipRole.PROVIDER, "analyst_agent"),
        (MembershipRole.RECEPTIONIST, "business_manager_agent"),
        (MembershipRole.PROVIDER, "billing_agent"),
    ],
)
async def test_front_desk_staff_cannot_reach_the_owner_agents(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, as_owner, salon, role, agent
):
    """Refused on role before the plan is read, so no plan hides the reason."""
    tenant, business = salon
    principal = await _staff(db_session, as_owner, tenant, role)
    app.dependency_overrides[get_principal] = lambda: principal
    _engine_off(app)

    assert _refused(await _ask(client, tenant, business, agent))


async def test_a_manager_reaches_the_accountant(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, as_owner, salon
):
    tenant, business = salon
    principal = await _staff(db_session, as_owner, tenant, MembershipRole.MANAGER)
    app.dependency_overrides[get_principal] = lambda: principal
    _engine_off(app)

    response = await _ask(client, tenant, business, "accountant_agent")

    assert response.status_code == 200, response.text
    assert response.json()["agent"] == "accountant_agent"
