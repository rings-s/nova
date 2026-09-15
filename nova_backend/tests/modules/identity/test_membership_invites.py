"""The invite-token flow that replaced granting straight to `users.email`.

docs/14 TM-04: `MembershipService.grant` used to resolve the grantee with
`users.find_by_email`, so whoever registered an address first — not
necessarily who the inviter meant — received the membership. Proven live
against the running stack on 2026-09-15: pre-registering
`new.hire@pentest-salon.example` before the (simulated) owner invited it was
enough to receive `manager`, including read access to every customer's PII
and `VIEW_FINANCIALS`/`REFUND_PAYMENTS`.

These tests are the regression: the same pre-registration race must now gain
nothing without the token.

Needs Postgres. `test_membership_router.py` covers the day-to-day mechanics
(role changes, revocation, the last owner) through the same two-step flow.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, PrincipalKind, get_principal
from app.modules.identity.domain import MembershipRole
from app.modules.identity.models import Membership, Tenant, User


@pytest.fixture
async def owner(db_session: AsyncSession, tenant_factory, as_owner) -> tuple[Tenant, User]:
    tenant = await tenant_factory()
    owner_user = User(
        email=f"owner-{uuid4().hex[:8]}@example.com",
        full_name="Owner",
        password_hash="not-a-real-hash",
    )
    db_session.add(owner_user)
    await db_session.flush()
    async with as_owner():
        db_session.add(
            Membership(user_id=owner_user.id, tenant_id=tenant.id, role=MembershipRole.OWNER)
        )
        await db_session.flush()
    return tenant, owner_user


@pytest.fixture
def principal(owner: tuple[Tenant, User]) -> Principal:
    tenant, owner_user = owner
    return Principal(
        subject_id=owner_user.id, kind=PrincipalKind.STAFF, tenant_ids=frozenset({tenant.id})
    )


def _url(tenant: Tenant, suffix: str = "") -> str:
    return f"/api/v1/tenants/{tenant.id}/memberships{suffix}"


async def test_pre_registering_the_invited_address_gains_nothing_without_the_token(
    app,
    client: AsyncClient,
    db_session: AsyncSession,
    owner: tuple[Tenant, User],
) -> None:
    """The exact TM-04 exploit: register the address *before* the invite
    exists, then see what a plain login gets you."""
    tenant, _owner_user = owner
    attacker = User(
        email="future-hire@example.com",
        full_name="Not The Real Hire",
        password_hash="not-a-real-hash",
    )
    db_session.add(attacker)
    await db_session.flush()

    invited = await client.post(
        _url(tenant), json={"email": "future-hire@example.com", "role": "manager"}
    )
    assert invited.status_code == 201
    assert "token" in invited.json()

    # The pre-registered account, logging in with no token at all, holds
    # nothing at this tenant — matching an ordinary login, not a promotion.
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=attacker.id, kind=PrincipalKind.CUSTOMER
    )
    tenants = await client.get("/api/v1/tenants")
    assert tenants.status_code == 200
    assert tenants.json()["items"] == []

    staff_only = await client.get(_url(tenant))
    assert staff_only.status_code == 403


async def test_the_invite_carries_no_link_to_any_account_until_accepted(
    client: AsyncClient, db_session: AsyncSession, owner: tuple[Tenant, User]
) -> None:
    """A pending invite is not a membership row at all — nothing to revoke,
    nothing granting access, until someone redeems its token."""
    tenant, _owner_user = owner

    response = await client.post(
        _url(tenant), json={"email": "someone@example.com", "role": "receptionist"}
    )
    body = response.json()
    assert "user_id" not in body
    assert body["token"]

    from sqlalchemy import func, select

    count = await db_session.execute(select(func.count()).select_from(Membership))
    assert count.scalar_one() == 1  # the owner's own seeded membership, and nothing else


async def test_accepting_requires_the_exact_token(
    app, client: AsyncClient, db_session: AsyncSession, owner: tuple[Tenant, User]
) -> None:
    tenant, _owner_user = owner
    real_hire = User(
        email="real-hire@example.com", full_name="Real Hire", password_hash="not-a-real-hash"
    )
    db_session.add(real_hire)
    await db_session.flush()

    invited = await client.post(
        _url(tenant), json={"email": "real-hire@example.com", "role": "receptionist"}
    )
    invite_id = invited.json()["id"]

    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=real_hire.id, kind=PrincipalKind.CUSTOMER
    )

    wrong = await client.post(
        _url(tenant, f"/invites/{invite_id}/accept"), json={"token": "wrong-token"}
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "invalid_invite"

    right = await client.post(
        _url(tenant, f"/invites/{invite_id}/accept"), json={"token": invited.json()["token"]}
    )
    assert right.status_code == 201
    assert right.json()["role"] == "receptionist"
    assert right.json()["user_id"] == str(real_hire.id)


async def test_a_service_principal_cannot_accept_an_invite(
    app, client: AsyncClient, owner: tuple[Tenant, User]
) -> None:
    """SERVICE has no `users` row to hold a membership on — and already
    reaches every tenant, so an invite is not for it anyway."""
    tenant, _owner_user = owner
    invited = await client.post(
        _url(tenant), json={"email": "someone@example.com", "role": "receptionist"}
    )
    body = invited.json()

    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=uuid4(), kind=PrincipalKind.SERVICE
    )
    response = await client.post(
        _url(tenant, f"/invites/{body['id']}/accept"), json={"token": body["token"]}
    )

    assert response.status_code == 403


async def test_pending_invites_are_listed_without_their_tokens(
    client: AsyncClient, owner: tuple[Tenant, User]
) -> None:
    tenant, _owner_user = owner
    await client.post(_url(tenant), json={"email": "pending@example.com", "role": "provider"})

    listed = await client.get(_url(tenant, "/invites"))

    assert listed.status_code == 200
    rows = listed.json()["items"]
    assert len(rows) == 1
    assert rows[0]["email"] == "pending@example.com"
    assert "token" not in rows[0]


async def test_an_expired_invite_is_refused(
    app, client: AsyncClient, db_session: AsyncSession, owner: tuple[Tenant, User], as_owner
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.modules.identity.models import MembershipInvite
    from app.modules.identity.service import _hash_invite_token

    tenant, _owner_user = owner
    late_hire = User(email="late@example.com", full_name="Late", password_hash="not-a-real-hash")
    db_session.add(late_hire)
    await db_session.flush()

    invite = MembershipInvite(
        tenant_id=tenant.id,
        email="late@example.com",
        role=MembershipRole.RECEPTIONIST,
        token_hash=_hash_invite_token("a-real-token"),
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    async with as_owner():
        db_session.add(invite)
        await db_session.flush()

    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=late_hire.id, kind=PrincipalKind.CUSTOMER
    )
    response = await client.post(
        _url(tenant, f"/invites/{invite.id}/accept"), json={"token": "a-real-token"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_invite"
