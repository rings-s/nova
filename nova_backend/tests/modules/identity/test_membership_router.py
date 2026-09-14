"""Membership management, end to end through the API.

Needs Postgres. The rules under test are the ones that make a salon
administrable by more than one person, and each has a specific failure mode
that is expensive in production:

  - a re-grant that INSERTs instead of reinstating is an `IntegrityError`,
    because `uq_memberships_user_tenant` has no `is_active` predicate;
  - removing the last owner leaves a business nobody can administer, with no
    self-service way back;
  - a role check read from the token rather than from this tenant's row lets a
    receptionist at one salon act as an owner at another.

Note on RLS: `memberships` carries the `tenant_isolation` policy, and the suite
runs as `nova_app`, which that policy applies to, so every request here goes
through it. Only the fixtures seed memberships as the owner.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, PrincipalKind
from app.modules.identity.domain import MembershipRole
from app.modules.identity.models import Membership, Tenant, User


@pytest.fixture
def user_factory(db_session: AsyncSession):
    async def _create(**overrides: object) -> User:
        defaults: dict[str, object] = {
            "email": f"staff-{uuid4().hex[:8]}@example.com",
            "full_name": "Test Person",
            "password_hash": "not-a-real-hash",
        }
        defaults.update(overrides)
        user = User(**defaults)
        db_session.add(user)
        await db_session.flush()
        return user

    return _create


@pytest.fixture
def membership_factory(db_session: AsyncSession, as_owner):
    async def _create(user: User, tenant: Tenant, role: MembershipRole) -> Membership:
        membership = Membership(user_id=user.id, tenant_id=tenant.id, role=role)
        async with as_owner():
            db_session.add(membership)
            await db_session.flush()
        return membership

    return _create


class Salon:
    """The tenant under test plus the people in it."""

    def __init__(self, tenant: Tenant, owner: User) -> None:
        self.tenant = tenant
        self.owner = owner


@pytest.fixture
async def salon(tenant_factory, user_factory, membership_factory) -> Salon:
    tenant = await tenant_factory()
    owner = await user_factory(email=f"owner-{uuid4().hex[:8]}@example.com")
    await membership_factory(owner, tenant, MembershipRole.OWNER)
    return Salon(tenant, owner)


@pytest.fixture
def principal(salon: Salon) -> Principal:
    """Overrides conftest's SERVICE principal.

    A SERVICE principal skips the role matrix entirely, which would make every
    test below pass for the wrong reason.
    """
    return Principal(
        subject_id=salon.owner.id,
        kind=PrincipalKind.STAFF,
        tenant_ids=frozenset({salon.tenant.id}),
    )


def _url(salon: Salon, suffix: str = "") -> str:
    return f"/api/v1/tenants/{salon.tenant.id}/memberships{suffix}"


async def _count_rows(session: AsyncSession, user: User, tenant: Tenant) -> int:
    stmt = (
        select(func.count())
        .select_from(Membership)
        .where(Membership.user_id == user.id, Membership.tenant_id == tenant.id)
    )
    return int((await session.execute(stmt)).scalar_one())


# --- granting -------------------------------------------------------------


async def test_owner_grants_access_to_an_existing_account(
    client: AsyncClient, salon: Salon, user_factory
) -> None:
    colleague = await user_factory(email="new-hire@example.com", full_name="New Hire")

    response = await client.post(
        _url(salon), json={"email": "new-hire@example.com", "role": "receptionist"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == str(colleague.id)
    assert body["role"] == "receptionist"
    assert body["email"] == "new-hire@example.com"
    assert body["full_name"] == "New Hire"
    assert body["is_active"] is True


async def test_grant_matches_the_address_case_insensitively(
    client: AsyncClient, salon: Salon, user_factory
) -> None:
    """Emails are stored lowercased at registration; a caller types what they
    remember."""
    await user_factory(email="mixed.case@example.com")

    response = await client.post(
        _url(salon), json={"email": "Mixed.Case@Example.com", "role": "provider"}
    )

    assert response.status_code == 201


async def test_grant_to_an_unknown_address_is_404(client: AsyncClient, salon: Salon) -> None:
    """There is no invite flow yet: the account has to exist first."""
    response = await client.post(
        _url(salon), json={"email": "nobody@example.com", "role": "provider"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "user_not_found"


async def test_granting_twice_is_409_rather_than_a_silent_role_change(
    client: AsyncClient, salon: Salon, user_factory
) -> None:
    await user_factory(email="already@example.com")
    payload = {"email": "already@example.com", "role": "receptionist"}

    assert (await client.post(_url(salon), json=payload)).status_code == 201

    second = await client.post(_url(salon), json={**payload, "role": "manager"})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_membership"


async def test_regrant_after_revoke_reinstates_the_same_row(
    client: AsyncClient, db_session: AsyncSession, salon: Salon, user_factory
) -> None:
    """The constraint has no `is_active` predicate, so a second INSERT for the
    same (user, tenant) is an IntegrityError. Re-hiring must flip the row."""
    returner = await user_factory(email="boomerang@example.com")
    payload = {"email": "boomerang@example.com", "role": "provider"}

    granted = await client.post(_url(salon), json=payload)
    membership_id = granted.json()["id"]

    revoked = await client.delete(_url(salon, f"/{membership_id}"))
    assert revoked.status_code == 200
    assert revoked.json()["is_active"] is False

    regranted = await client.post(_url(salon), json={**payload, "role": "manager"})
    assert regranted.status_code == 201
    assert regranted.json()["id"] == membership_id
    assert regranted.json()["role"] == "manager"
    assert regranted.json()["is_active"] is True

    assert await _count_rows(db_session, returner, salon.tenant) == 1


# --- listing --------------------------------------------------------------


async def test_list_shows_active_members_only(
    client: AsyncClient, salon: Salon, user_factory
) -> None:
    await user_factory(email="stays@example.com")
    await user_factory(email="leaves@example.com")

    await client.post(_url(salon), json={"email": "stays@example.com", "role": "provider"})
    leaving = await client.post(
        _url(salon), json={"email": "leaves@example.com", "role": "provider"}
    )
    await client.delete(_url(salon, f"/{leaving.json()['id']}"))

    listed = await client.get(_url(salon))
    assert listed.status_code == 200
    emails = {row["email"] for row in listed.json()["items"]}
    assert "stays@example.com" in emails
    assert "leaves@example.com" not in emails


# --- role changes ---------------------------------------------------------


async def test_owner_changes_a_colleagues_role(
    client: AsyncClient, salon: Salon, user_factory
) -> None:
    await user_factory(email="promoted@example.com")
    granted = await client.post(
        _url(salon), json={"email": "promoted@example.com", "role": "receptionist"}
    )

    response = await client.patch(_url(salon, f"/{granted.json()['id']}"), json={"role": "manager"})

    assert response.status_code == 200
    assert response.json()["role"] == "manager"


async def test_patching_a_revoked_membership_is_404(
    client: AsyncClient, salon: Salon, user_factory
) -> None:
    """A revoked membership is history; the way back is a fresh grant."""
    await user_factory(email="gone@example.com")
    granted = await client.post(_url(salon), json={"email": "gone@example.com", "role": "provider"})
    await client.delete(_url(salon, f"/{granted.json()['id']}"))

    response = await client.patch(_url(salon, f"/{granted.json()['id']}"), json={"role": "manager"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "membership_not_found"


async def test_unknown_membership_is_404(client: AsyncClient, salon: Salon) -> None:
    response = await client.delete(_url(salon, f"/{uuid4()}"))
    assert response.status_code == 404


# --- the last owner -------------------------------------------------------


async def test_the_last_owner_cannot_be_revoked(
    client: AsyncClient, db_session: AsyncSession, salon: Salon, as_owner
) -> None:
    """Otherwise the business is unadministrable with no self-service way back."""
    stmt = select(Membership).where(
        Membership.user_id == salon.owner.id, Membership.tenant_id == salon.tenant.id
    )
    # No request has scoped this transaction yet, so RLS would hide the row.
    async with as_owner():
        membership = (await db_session.execute(stmt)).scalar_one()

    response = await client.delete(_url(salon, f"/{membership.id}"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_owner"


async def test_the_last_owner_cannot_be_demoted(
    client: AsyncClient, db_session: AsyncSession, salon: Salon, as_owner
) -> None:
    """Demotion is the same hole as removal, reached differently."""
    stmt = select(Membership).where(
        Membership.user_id == salon.owner.id, Membership.tenant_id == salon.tenant.id
    )
    async with as_owner():
        membership = (await db_session.execute(stmt)).scalar_one()

    response = await client.patch(_url(salon, f"/{membership.id}"), json={"role": "manager"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_owner"


async def test_an_owner_may_step_down_once_there_is_a_second_one(
    client: AsyncClient, db_session: AsyncSession, salon: Salon, user_factory
) -> None:
    await user_factory(email="co-owner@example.com")
    await client.post(_url(salon), json={"email": "co-owner@example.com", "role": "owner"})

    stmt = select(Membership).where(
        Membership.user_id == salon.owner.id, Membership.tenant_id == salon.tenant.id
    )
    membership = (await db_session.execute(stmt)).scalar_one()

    response = await client.patch(_url(salon, f"/{membership.id}"), json={"role": "manager"})

    assert response.status_code == 200
    assert response.json()["role"] == "manager"


# --- authority ------------------------------------------------------------


class TestRank:
    """Authority is read from this tenant's `memberships` row, never the token.

    `Principal.roles` is minted from every membership a user holds across all
    tenants and flattened into one set with no tenant key, so an owner of salon
    A who answers the phone at salon B carries {"owner", "receptionist"} at
    both. These tests fix a token claim that says "owner" against a database
    row that does not, and require the database to win.
    """

    @pytest.fixture
    async def manager(self, salon: Salon, user_factory, membership_factory) -> User:
        user = await user_factory(email=f"manager-{uuid4().hex[:8]}@example.com")
        await membership_factory(user, salon.tenant, MembershipRole.MANAGER)
        return user

    async def test_a_manager_may_appoint_a_receptionist(
        self, app, client: AsyncClient, salon: Salon, manager: User, user_factory
    ) -> None:
        from app.core.security import get_principal

        app.dependency_overrides[get_principal] = lambda: Principal(
            subject_id=manager.id,
            kind=PrincipalKind.STAFF,
            tenant_ids=frozenset({salon.tenant.id}),
        )
        await user_factory(email="front-desk@example.com")

        response = await client.post(
            _url(salon), json={"email": "front-desk@example.com", "role": "receptionist"}
        )

        assert response.status_code == 201

    async def test_a_manager_cannot_appoint_an_owner(
        self, app, client: AsyncClient, salon: Salon, manager: User, user_factory
    ) -> None:
        """Otherwise 'manager' is 'owner' with one extra step."""
        from app.core.security import get_principal

        app.dependency_overrides[get_principal] = lambda: Principal(
            subject_id=manager.id,
            kind=PrincipalKind.STAFF,
            tenant_ids=frozenset({salon.tenant.id}),
            roles=frozenset({"owner"}),
        )
        await user_factory(email="usurper@example.com")

        response = await client.post(
            _url(salon), json={"email": "usurper@example.com", "role": "owner"}
        )

        assert response.status_code == 403

    async def test_a_staff_principal_with_no_membership_here_manages_nobody(
        self, app, client: AsyncClient, salon: Salon, user_factory
    ) -> None:
        """The token claims this tenant and the role; the table says otherwise."""
        from app.core.security import get_principal

        outsider = await user_factory(email="outsider@example.com")
        app.dependency_overrides[get_principal] = lambda: Principal(
            subject_id=outsider.id,
            kind=PrincipalKind.STAFF,
            tenant_ids=frozenset({salon.tenant.id}),
            roles=frozenset({"owner"}),
        )
        await user_factory(email="target@example.com")

        response = await client.post(
            _url(salon), json={"email": "target@example.com", "role": "provider"}
        )

        assert response.status_code == 403

    async def test_a_customer_principal_is_refused_before_the_matrix(
        self, app, client: AsyncClient, salon: Salon
    ) -> None:
        """Customers reach every tenant now; `require_staff` is what keeps that
        from reaching the staff list."""
        from app.core.security import get_principal

        app.dependency_overrides[get_principal] = lambda: Principal(
            subject_id=uuid4(), kind=PrincipalKind.CUSTOMER
        )

        assert (await client.get(_url(salon))).status_code == 403
