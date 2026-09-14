"""Marketplace attribution — the writer ADR-0008 deferred until now.

`BookingSource.MARKETPLACE` is the only source that can ever cost a salon
money (35% of the service price, docs/11 section 3 rule 1). ADR-0008 froze it
with no writer because nothing could verify the claim:

    "It has to be derived server-side from a marketplace attribution record —
     the 30-day click window in docs/11 section 3 rule 4 — and that needs the
     public discovery surface, which does not exist."

These are the tests for that derivation. Every one of them is really the same
assertion from a different angle: NOVA charges only when it can *prove* it
introduced the customer, and every unprovable case falls back to the free
`direct_link` default, because docs/11 names the opposite mistake a P1:

    "A customer is charged as 'new' exactly once, per business, forever. Any
     bug that re-charges an existing customer is a P1."
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, PrincipalKind, get_principal
from app.modules.discovery.domain import hash_referral_token
from app.modules.discovery.models import MarketplaceReferral
from app.modules.identity.models import User

DISCOVERY = "/api/v1/discovery"


@pytest_asyncio.fixture
async def signed_in_customer(db_session: AsyncSession) -> User:
    """A person with an account, booking for themselves.

    Self-service is what a marketplace booking *is*: staff booking on behalf of
    someone at the counter is `RECEPTION` by definition, and can never be
    attributed to NOVA however many referral tokens are attached.
    """
    user = User(
        email=f"customer-{uuid4().hex[:8]}@example.com",
        # Required: `ensure_for_user` refuses to provision a customer record
        # without one, because a salon that cannot reach the customer cannot
        # confirm the booking by WhatsApp.
        phone=f"+96650{uuid4().int % 10_000_000:07d}",
        full_name="Noura",
        password_hash="not-a-real-hash",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def customer_client(db_session: AsyncSession, signed_in_customer: User) -> AsyncClient:
    """A client authenticated as that customer, not as the default service principal."""
    from app.core.deps import get_db_session
    from app.main import create_app

    application: FastAPI = create_app()

    async def _session():
        yield db_session

    async def _principal() -> Principal:
        return Principal(subject_id=signed_in_customer.id, kind=PrincipalKind.CUSTOMER)

    application.dependency_overrides[get_db_session] = _session
    application.dependency_overrides[get_principal] = _principal
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def salon(
    tenant_factory, business_factory, location_factory, service_factory, provider_factory, qualify
):
    """A bookable salon, published on the marketplace."""

    class Salon:
        pass

    salon = Salon()
    salon.tenant = await tenant_factory()
    salon.business = await business_factory(salon.tenant, slug=f"salon-{uuid4().hex[:8]}")
    salon.location = await location_factory(salon.business)
    salon.service = await service_factory(salon.location)
    salon.provider = await provider_factory(salon.location)
    await qualify(salon.provider, salon.service)
    return salon


def booking_payload(salon, *, days_ahead: int = 3, **extra):
    return {
        "location_id": str(salon.location.id),
        "service_id": str(salon.service.id),
        "provider_id": str(salon.provider.id),
        "starts_at": (datetime.now(UTC) + timedelta(days=days_ahead))
        .replace(microsecond=0)
        .isoformat(),
        **extra,
    }


async def test_a_booking_after_a_marketplace_click_is_billable(customer_client, salon):
    """The whole point: discovery → referral → booking → `marketplace`.

    Before this existed, this booking was recorded as `direct_link` and the
    commission line accrued 0.00 (ADR-0009). It is the first path in NOVA that
    can produce a chargeable booking at all.
    """
    referral = await customer_client.post(f"{DISCOVERY}/businesses/{salon.business.slug}/referrals")
    assert referral.status_code == 201
    token = referral.json()["referral_token"]

    booked = await customer_client.post(
        f"/api/v1/tenants/{salon.tenant.id}/bookings",
        json=booking_payload(salon, referral_token=token),
    )

    assert booked.status_code == 201, booked.text
    assert booked.json()["source"] == "marketplace"


async def test_a_booking_with_no_referral_is_free(customer_client, salon):
    """The default, and the one uncertainty resolves to."""
    booked = await customer_client.post(
        f"/api/v1/tenants/{salon.tenant.id}/bookings",
        json=booking_payload(salon),
    )

    assert booked.status_code == 201, booked.text
    assert booked.json()["source"] == "direct_link"


async def test_a_client_still_cannot_simply_declare_marketplace(customer_client, salon):
    """ADR-0008's rule survives the arrival of a writer.

    A client that could assert this could invent revenue; one that could
    withhold it could dodge a charge it owed. The marketplace does not declare
    the source either — it presents a token the server issued.
    """
    refused = await customer_client.post(
        f"/api/v1/tenants/{salon.tenant.id}/bookings",
        json=booking_payload(salon, source="marketplace"),
    )
    assert refused.status_code == 403


async def test_a_referral_for_one_salon_cannot_be_spent_at_another(
    customer_client,
    salon,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
):
    """The cheapest attribution fraud available, and the only one a client can
    attempt by hand: click a listing that costs nothing, then attach the token
    to a booking somewhere else."""
    other_tenant = await tenant_factory()
    other_business = await business_factory(other_tenant, slug=f"other-{uuid4().hex[:8]}")
    other_location = await location_factory(other_business)
    other_service = await service_factory(other_location)
    other_provider = await provider_factory(other_location)
    await qualify(other_provider, other_service)

    stolen = (
        await customer_client.post(f"{DISCOVERY}/businesses/{other_business.slug}/referrals")
    ).json()["referral_token"]

    booked = await customer_client.post(
        f"/api/v1/tenants/{salon.tenant.id}/bookings",
        json=booking_payload(salon, referral_token=stolen),
    )

    assert booked.status_code == 201
    assert booked.json()["source"] == "direct_link"


async def test_an_expired_referral_does_not_attribute(
    customer_client, salon, db_session: AsyncSession
):
    """docs/11 section 3 rule 4: "A booking outside the window with no prior
    marketplace touch is direct." """
    token = (
        await customer_client.post(f"{DISCOVERY}/businesses/{salon.business.slug}/referrals")
    ).json()["referral_token"]

    referral = (
        await db_session.execute(
            select(MarketplaceReferral).where(
                MarketplaceReferral.token_hash == hash_referral_token(token)
            )
        )
    ).scalar_one()
    referral.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()

    booked = await customer_client.post(
        f"/api/v1/tenants/{salon.tenant.id}/bookings",
        json=booking_payload(salon, referral_token=token),
    )

    assert booked.status_code == 201
    assert booked.json()["source"] == "direct_link"


async def test_an_invented_token_does_not_attribute(customer_client, salon):
    """A forged token is not an error, it is simply not a marketplace booking.

    Rejecting the booking would let anyone break a salon's checkout by
    attaching junk; the honest outcome is the free default.
    """
    booked = await customer_client.post(
        f"/api/v1/tenants/{salon.tenant.id}/bookings",
        json=booking_payload(salon, referral_token="not-a-real-token"),
    )

    assert booked.status_code == 201
    assert booked.json()["source"] == "direct_link"


async def test_reception_is_never_upgraded_by_a_referral(client, salon, customer_factory):
    """Staff booking at the counter is `RECEPTION`, whatever is attached.

    `resolve_booking_source` settles this before attribution is consulted, and
    the ordering matters: reception is a counter action, and nothing else it
    could claim is true.
    """
    walk_in = await customer_factory(salon.tenant)
    token = (await client.post(f"{DISCOVERY}/businesses/{salon.business.slug}/referrals")).json()[
        "referral_token"
    ]

    booked = await client.post(
        f"/api/v1/tenants/{salon.tenant.id}/bookings",
        json=booking_payload(
            salon,
            referral_token=token,
            on_behalf_of_customer_id=str(walk_in.id),
        ),
    )

    assert booked.status_code == 201
    assert booked.json()["source"] == "reception"


async def test_a_declared_channel_the_salon_owns_is_not_upgraded(customer_client, salon):
    """A WhatsApp booking is the salon's own channel and stays free.

    Only the unattributed `direct_link` default is ever upgraded — otherwise a
    stray token re-labels a booking the salon earned itself as one NOVA is owed
    35% on.
    """
    token = (
        await customer_client.post(f"{DISCOVERY}/businesses/{salon.business.slug}/referrals")
    ).json()["referral_token"]

    booked = await customer_client.post(
        f"/api/v1/tenants/{salon.tenant.id}/bookings",
        json=booking_payload(salon, referral_token=token, source="whatsapp"),
    )

    assert booked.status_code == 201
    assert booked.json()["source"] == "whatsapp"


async def test_the_token_is_never_stored(customer_client, salon, db_session: AsyncSession):
    """Reading the referrals table must not hand anyone a working token.

    The rows decide what a salon is invoiced; they should not double as a
    supply of the credentials that produce those invoices.
    """
    token = (
        await customer_client.post(f"{DISCOVERY}/businesses/{salon.business.slug}/referrals")
    ).json()["referral_token"]

    stored = (
        (
            await db_session.execute(
                select(MarketplaceReferral).where(
                    MarketplaceReferral.business_id == salon.business.id
                )
            )
        )
        .scalars()
        .all()
    )

    assert stored
    assert all(row.token_hash != token for row in stored)
    assert all(row.token_hash == hash_referral_token(token) for row in stored)


async def test_the_referral_records_which_booking_claimed_it(
    customer_client, salon, db_session: AsyncSession
):
    """The audit trail behind a commission line.

    A disputed invoice is settled by showing the salon which click produced
    which booking, which is why the row is stamped rather than deleted.
    """
    token = (
        await customer_client.post(f"{DISCOVERY}/businesses/{salon.business.slug}/referrals")
    ).json()["referral_token"]

    booked = await customer_client.post(
        f"/api/v1/tenants/{salon.tenant.id}/bookings",
        json=booking_payload(salon, referral_token=token),
    )
    assert booked.json()["source"] == "marketplace"

    referral = (
        await db_session.execute(
            select(MarketplaceReferral).where(
                MarketplaceReferral.token_hash == hash_referral_token(token)
            )
        )
    ).scalar_one()

    assert referral.consumed_at is not None
    assert str(referral.consumed_by_booking_id) == booked.json()["id"]


async def test_a_referral_cannot_be_recorded_for_a_delisted_salon(
    customer_client, salon, db_session: AsyncSession, as_owner
):
    """No storefront, no click. A salon hidden for non-payment cannot accrue
    marketplace commission while it is off the marketplace."""
    # As the owner, so no tenant scope outlives the change into the request.
    async with as_owner():
        salon.business.is_listed = False
        await db_session.flush()

    refused = await customer_client.post(f"{DISCOVERY}/businesses/{salon.business.slug}/referrals")
    assert refused.status_code == 404
