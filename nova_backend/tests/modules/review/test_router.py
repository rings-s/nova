"""Verified reviews over HTTP, and the marketplace ranking they feed.

The property under test throughout: a rating can only come from the customer
whose completed visit it describes, once — because that is what makes "top
rated" on the public marketplace mean anything.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, PrincipalKind, get_principal
from app.db.session import set_tenant_scope
from app.modules.booking.models import BookingRecord
from app.modules.catalog.models import Business
from app.modules.identity.models import User

DISCOVERY = "/api/v1/discovery"


def _reviews(tenant_id) -> str:
    return f"/api/v1/tenants/{tenant_id}/reviews"


@pytest.fixture
async def visit(
    db_session: AsyncSession,
    as_owner,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    customer_factory,
):
    """A customer account with one booking at a listed salon, status to taste."""

    async def _make(status: str = "completed", *, business=None, user=None):
        if business is None:
            business = await business_factory(await tenant_factory())
            location = await location_factory(business, city="Riyadh")
        else:
            location = await location_factory(business, city="Riyadh")
        service = await service_factory(location)
        provider = await provider_factory(location)
        if user is None:
            user = User(
                email=f"guest-{uuid4().hex[:8]}@example.com",
                full_name="Guest",
                password_hash="not-a-real-hash",
            )
            db_session.add(user)
            await db_session.flush()
        # The factory reads only `.id` off the tenant.
        customer = await customer_factory(SimpleNamespace(id=business.tenant_id), user_id=user.id)
        await set_tenant_scope(db_session, business.tenant_id)
        start = datetime.now(UTC) - timedelta(days=1)
        booking = BookingRecord(
            tenant_id=business.tenant_id,
            business_id=business.id,
            location_id=location.id,
            service_id=service.id,
            provider_id=provider.id,
            customer_id=customer.id,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            price=Decimal("150.00"),
            currency="SAR",
            status=status,
            source="direct_link",
        )
        db_session.add(booking)
        await db_session.flush()
        principal = Principal(subject_id=user.id, kind=PrincipalKind.CUSTOMER)
        return business, booking, principal

    return _make


def _as(app, principal: Principal) -> None:
    app.dependency_overrides[get_principal] = lambda: principal


async def _totals(db_session: AsyncSession, as_owner, business_id) -> tuple[int, int]:
    async with as_owner():
        business = (
            await db_session.execute(
                select(Business)
                .where(Business.id == business_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        return business.rating_count, business.rating_sum


async def test_a_customer_rates_their_completed_visit(app, client, db_session, as_owner, visit):
    business, booking, customer = await visit()
    _as(app, customer)

    response = await client.post(
        _reviews(business.tenant_id),
        json={"booking_id": str(booking.id), "rating": 5, "comment": "  Wonderful  "},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["rating"] == 5
    assert body["comment"] == "Wonderful"
    assert await _totals(db_session, as_owner, business.id) == (1, 5)


async def test_a_visit_is_rated_once(app, client, db_session, as_owner, visit):
    business, booking, customer = await visit()
    _as(app, customer)
    payload = {"booking_id": str(booking.id), "rating": 4}

    first = await client.post(_reviews(business.tenant_id), json=payload)
    second = await client.post(_reviews(business.tenant_id), json=payload | {"rating": 1})

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "already_reviewed"
    assert await _totals(db_session, as_owner, business.id) == (1, 4)


@pytest.mark.parametrize("status", ["confirmed", "cancelled", "no_show"])
async def test_only_a_completed_visit_can_be_rated(app, client, visit, status):
    business, booking, customer = await visit(status)
    _as(app, customer)

    response = await client.post(
        _reviews(business.tenant_id), json={"booking_id": str(booking.id), "rating": 5}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "review_not_allowed"


async def test_nobody_rates_someone_elses_visit(app, client, db_session, visit):
    business, booking, _owner = await visit()
    stranger = User(
        email=f"stranger-{uuid4().hex[:8]}@example.com",
        full_name="Stranger",
        password_hash="not-a-real-hash",
    )
    db_session.add(stranger)
    await db_session.flush()
    _as(app, Principal(subject_id=stranger.id, kind=PrincipalKind.CUSTOMER))

    response = await client.post(
        _reviews(business.tenant_id), json={"booking_id": str(booking.id), "rating": 5}
    )

    # 404, not 403: confirming the booking exists would be an enumeration oracle.
    assert response.status_code == 404


async def test_staff_cannot_rate_their_own_salon(app, client, visit):
    business, booking, _customer = await visit()
    _as(
        app,
        Principal(
            subject_id=uuid4(), kind=PrincipalKind.STAFF, tenant_ids=frozenset({business.tenant_id})
        ),
    )

    response = await client.post(
        _reviews(business.tenant_id), json={"booking_id": str(booking.id), "rating": 5}
    )

    assert response.status_code == 403


async def test_a_rating_is_one_to_five_stars(app, client, visit):
    business, booking, customer = await visit()
    _as(app, customer)

    response = await client.post(
        _reviews(business.tenant_id), json={"booking_id": str(booking.id), "rating": 6}
    )

    assert response.status_code == 422


async def test_a_customer_sees_what_they_have_rated(app, client, visit):
    business, booking, customer = await visit()
    _as(app, customer)
    await client.post(
        _reviews(business.tenant_id), json={"booking_id": str(booking.id), "rating": 3}
    )

    mine = await client.get(_reviews(business.tenant_id) + "/mine")

    assert mine.status_code == 200
    assert [r["booking_id"] for r in mine.json()] == [str(booking.id)]


async def test_staff_read_the_comments_the_public_never_sees(app, client, visit, principal):
    business, booking, customer = await visit()
    _as(app, customer)
    await client.post(
        _reviews(business.tenant_id),
        json={"booking_id": str(booking.id), "rating": 2, "comment": "Waited 40 minutes"},
    )

    _as(app, principal)  # the suite's SERVICE principal: staff-level
    staff_view = await client.get(
        _reviews(business.tenant_id), params={"business_id": str(business.id)}
    )
    storefront = await client.get(f"{DISCOVERY}/businesses/{business.slug}")

    assert staff_view.status_code == 200
    assert staff_view.json()["items"][0]["comment"] == "Waited 40 minutes"
    assert "Waited 40 minutes" not in storefront.text
    assert storefront.json()["rating_count"] == 1
    assert storefront.json()["rating_average"] == 2.0


async def test_top_rated_weighs_evidence_not_just_the_average(
    client, db_session, as_owner, tenant_factory, business_factory, location_factory
):
    """One 5-star visit must not outrank two hundred visits averaging 4.8."""
    tag = uuid4().hex[:6]
    lucky = await business_factory(await tenant_factory(), name_en=f"Rank {tag} Lucky")
    proven = await business_factory(await tenant_factory(), name_en=f"Rank {tag} Proven")
    unrated = await business_factory(await tenant_factory(), name_en=f"Rank {tag} Unrated")
    for business in (lucky, proven, unrated):
        await location_factory(business)
    async with as_owner():
        lucky.rating_count, lucky.rating_sum = 1, 5
        proven.rating_count, proven.rating_sum = 200, 960
        await db_session.flush()

    ranked = await client.get(
        DISCOVERY + "/businesses", params={"q": f"Rank {tag}", "sort": "rating"}
    )

    assert ranked.status_code == 200
    names = [item["name_en"] for item in ranked.json()["items"]]
    assert names == [f"Rank {tag} Proven", f"Rank {tag} Lucky", f"Rank {tag} Unrated"]
    proven_card = ranked.json()["items"][0]
    assert proven_card["rating_count"] == 200
    assert proven_card["rating_average"] == 4.8


async def test_sorting_by_distance_needs_a_position(client):
    response = await client.get(DISCOVERY + "/businesses", params={"sort": "distance"})

    assert response.status_code == 422
