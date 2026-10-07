"""A staff account is staff only where it works, and a customer everywhere else
(ADR-0016). Needs Postgres; runs the real token path, as
`test_token_revocation.py` does.

Before, any membership made an account STAFF everywhere, and STAFF reaches only
its own tenants: a stylist could not book a treatment at another salon.
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
    application: FastAPI = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _accounts(subject_id: UUID):
        return await token_state_in(db_session, subject_id)

    application.dependency_overrides[get_db_session] = _session
    application.dependency_overrides[get_token_state_lookup] = lambda: _accounts
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as c:
        yield c
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def stylist(db_session: AsyncSession, as_owner, tenant_factory):
    """A stylist at one salon, and a second salon they do not work for."""
    own, other = await tenant_factory(), await tenant_factory()
    user = User(
        email=f"stylist-{uuid4().hex[:8]}@example.com",
        full_name="Huda",
        password_hash="not-a-real-hash",
        phone=f"+9665{uuid4().int % 10**8:08d}",
    )
    db_session.add(user)
    await db_session.flush()
    async with as_owner():
        db_session.add(Membership(tenant_id=own.id, user_id=user.id, role=MembershipRole.PROVIDER))
        await db_session.flush()
    token = issue_token(
        subject_id=user.id,
        kind=PrincipalKind.STAFF,
        secret=get_settings().secret_key,
        tenant_ids={own.id},
        token_version=user.token_version,
    )
    return {"own": own, "other": other, "headers": {"Authorization": f"Bearer {token}"}}


async def test_a_stylist_reaches_another_salon_as_a_customer(authenticating_client, stylist):
    other = stylist["other"].id

    mine = await authenticating_client.get(
        f"/api/v1/tenants/{other}/bookings", headers=stylist["headers"]
    )

    # A customer's own bookings there (none yet), not a 403 for the tenant.
    assert mine.status_code == 200, mine.text
    assert mine.json()["items"] == []


async def test_a_stylist_has_no_staff_authority_at_another_salon(authenticating_client, stylist):
    other = stylist["other"].id

    refused = await authenticating_client.get(
        f"/api/v1/tenants/{other}/catalog/businesses", headers=stylist["headers"]
    )

    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "forbidden"


async def test_a_stylist_is_still_staff_at_their_own_salon(authenticating_client, stylist):
    own = stylist["own"].id

    allowed = await authenticating_client.get(
        f"/api/v1/tenants/{own}/catalog/businesses", headers=stylist["headers"]
    )

    assert allowed.status_code == 200, allowed.text
