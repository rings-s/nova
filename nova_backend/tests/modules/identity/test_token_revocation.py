"""Revoking an account's tokens takes effect on its next request.

Needs Postgres. Other API tests stub `get_principal`; these run the real token
path, reading the account through the test's own transaction. Before, an access
token outlived logout-everywhere, a revoked membership or a deactivated account
for up to its 15-minute lifetime.
"""

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session
from app.core.security import PrincipalKind, get_token_state_lookup, issue_token, token_state_in
from app.main import create_app
from app.modules.identity.domain import MembershipRole
from app.modules.identity.models import Membership, User


@pytest_asyncio.fixture
async def authenticating_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """A client whose bearer tokens are verified for real."""
    application: FastAPI = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _accounts(subject_id: UUID):
        return await token_state_in(db_session, subject_id)

    application.dependency_overrides[get_db_session] = _session
    application.dependency_overrides[get_token_state_lookup] = lambda: _accounts
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    application.dependency_overrides.clear()


async def _account(db_session: AsyncSession) -> User:
    user = User(
        email=f"person-{uuid4().hex[:8]}@example.com",
        full_name="Noura",
        password_hash="not-a-real-hash",
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _bearer(
    user: User,
    *,
    kind: PrincipalKind = PrincipalKind.CUSTOMER,
    tenant_ids: frozenset[UUID] = frozenset(),
) -> dict[str, str]:
    token = issue_token(
        subject_id=user.id,
        kind=kind,
        secret=get_settings().secret_key,
        tenant_ids=tenant_ids,
        token_version=user.token_version,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_logout_everywhere_ends_the_access_token_it_was_sent_with(
    authenticating_client: AsyncClient, db_session: AsyncSession
):
    user = await _account(db_session)
    headers = _bearer(user)
    assert (await authenticating_client.get("/api/v1/tenants", headers=headers)).status_code == 200

    logged_out = await authenticating_client.post("/api/v1/auth/logout-everywhere", headers=headers)
    assert logged_out.status_code == 204

    refused = await authenticating_client.get("/api/v1/tenants", headers=headers)
    assert refused.status_code == 401
    assert refused.json()["error"]["code"] == "unauthenticated"


async def test_a_deactivated_account_is_refused_at_once(
    authenticating_client: AsyncClient, db_session: AsyncSession
):
    user = await _account(db_session)
    headers = _bearer(user)
    assert (await authenticating_client.get("/api/v1/tenants", headers=headers)).status_code == 200

    user.is_active = False
    await db_session.flush()

    assert (await authenticating_client.get("/api/v1/tenants", headers=headers)).status_code == 401


async def test_revoking_a_membership_ends_that_persons_access_at_once(
    authenticating_client: AsyncClient,
    client: AsyncClient,
    db_session: AsyncSession,
    as_owner,
    tenant_factory,
):
    tenant = await tenant_factory()
    staff = await _account(db_session)
    async with as_owner():
        membership = Membership(
            user_id=staff.id, tenant_id=tenant.id, role=MembershipRole.RECEPTIONIST
        )
        db_session.add(membership)
        await db_session.flush()
    headers = _bearer(staff, kind=PrincipalKind.STAFF, tenant_ids=frozenset({tenant.id}))
    salon = f"/api/v1/tenants/{tenant.id}"
    assert (await authenticating_client.get(salon, headers=headers)).status_code == 200

    # Revoked by someone else: the conftest client's service principal.
    revoked = await client.delete(f"{salon}/memberships/{membership.id}")
    assert revoked.status_code == 200, revoked.text

    refused = await authenticating_client.get(salon, headers=headers)
    assert refused.status_code == 401
