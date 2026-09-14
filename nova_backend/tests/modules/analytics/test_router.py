"""The analytics HTTP surface (docs/13 section 9). Needs Postgres."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, PrincipalKind, get_principal
from app.core.values import TimeRange
from app.db.session import set_tenant_scope
from app.modules.booking.domain import BookingSource, BookingStatus
from app.modules.booking.models import BookingRecord
from app.modules.booking.repository import BookingRepository


@pytest_asyncio.fixture
async def salon(
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    customer_factory,
):
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    location = await location_factory(business)
    return {
        "tenant": tenant,
        "business": business,
        "location": location,
        "service": await service_factory(location),
        "provider": await provider_factory(location),
        "customer": await customer_factory(tenant),
    }


async def add_bookings(
    db_session: AsyncSession, salon: dict, *, count: int, status: BookingStatus, offset: int = 0
) -> None:
    """Rows written directly: the analytics surface reads history, it does not make it."""
    # In the salon's own scope, as the requests that made them were.
    await set_tenant_scope(db_session, salon["tenant"].id)
    first = (datetime.now(UTC) - timedelta(days=10)).replace(minute=0, second=0, microsecond=0)
    for i in range(count):
        starts = first + timedelta(hours=2 * (i + offset))
        db_session.add(
            BookingRecord(
                tenant_id=salon["tenant"].id,
                business_id=salon["business"].id,
                location_id=salon["location"].id,
                service_id=salon["service"].id,
                provider_id=salon["provider"].id,
                customer_id=salon["customer"].id,
                starts_at=starts,
                ends_at=starts + timedelta(hours=1),
                price=Decimal("150.00"),
                currency="SAR",
                status=status,
                source=BookingSource.DIRECT_LINK,
            )
        )
    await db_session.flush()


def url(salon: dict, path: str) -> str:
    return f"/api/v1/tenants/{salon['tenant'].id}/analytics/{path}"


async def test_the_overview_counts_what_happened(client: AsyncClient, db_session, salon):
    await add_bookings(db_session, salon, count=20, status=BookingStatus.COMPLETED)
    await add_bookings(db_session, salon, count=5, status=BookingStatus.CANCELLED, offset=20)

    response = await client.get(
        url(salon, "overview"), params={"business_id": str(salon["business"].id)}
    )

    assert response.status_code == 200
    body = response.json()
    kpis = {kpi["metric"]: kpi for kpi in body["kpis"]}
    assert kpis["bookings"]["value"] == "25"
    assert kpis["completed"]["value"] == "20"
    assert kpis["completion_rate"]["value"] == "0.8000"
    assert kpis["revenue"]["value"] == "3000.00"
    assert body["currency"] == "SAR"
    assert body["window"]["days"] == 30


async def test_a_customer_cannot_read_a_salons_numbers(app: FastAPI, client: AsyncClient, salon):
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=uuid4(), kind=PrincipalKind.CUSTOMER
    )
    response = await client.get(
        url(salon, "overview"), params={"business_id": str(salon["business"].id)}
    )
    assert response.status_code == 403


async def test_branch_comparison_needs_the_chain_plan(client: AsyncClient, db_session, salon):
    await add_bookings(db_session, salon, count=3, status=BookingStatus.COMPLETED)
    params = {"business_id": str(salon["business"].id)}

    by_location = await client.get(
        url(salon, "breakdown"), params={**params, "dimension": "location"}
    )
    by_service = await client.get(
        url(salon, "breakdown"), params={**params, "dimension": "service"}
    )

    # A business that never subscribed is on Solo (docs/11 section 2).
    assert by_location.status_code == 403
    assert by_location.json()["error"]["code"] == "plan_feature_required"
    assert by_service.status_code == 200
    assert by_service.json()["items"][0]["revenue"] == "450.00"


async def test_a_chart_is_plotly_json_in_the_requested_language(
    client: AsyncClient, db_session, salon
):
    await add_bookings(db_session, salon, count=4, status=BookingStatus.COMPLETED)
    params = {"business_id": str(salon["business"].id), "locale": "ar"}

    response = await client.get(url(salon, "charts/bookings_trend"), params=params)

    assert response.status_code == 200
    chart = response.json()
    assert chart["title"] == "الحجوزات ونتائجها"
    assert chart["figure"]["data"]
    assert "layout" in chart["figure"]


async def test_an_unknown_chart_is_not_found(client: AsyncClient, salon):
    response = await client.get(
        url(salon, "charts/revenue_by_horoscope"), params={"business_id": str(salon["business"].id)}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "chart_not_found"


async def test_the_catalog_lists_every_chart(client: AsyncClient, salon):
    response = await client.get(url(salon, "charts"))
    assert response.status_code == 200
    assert response.json()["total"] == 16


async def test_an_unbounded_window_is_refused(client: AsyncClient, salon):
    response = await client.get(
        url(salon, "overview"),
        params={"business_id": str(salon["business"].id), "date_from": "2020-01-01"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "report_window_invalid"


async def test_a_forecast_without_history_is_refused(client: AsyncClient, salon):
    response = await client.get(
        url(salon, "forecast"), params={"business_id": str(salon["business"].id)}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "insufficient_data"


async def test_the_financial_summary_is_on_every_plan(client: AsyncClient, db_session, salon):
    await add_bookings(db_session, salon, count=2, status=BookingStatus.COMPLETED)
    response = await client.get(
        url(salon, "financial-summary"), params={"business_id": str(salon["business"].id)}
    )
    assert response.status_code == 200
    assert response.json()["revenue"] == "300.00"


async def test_another_tenants_business_is_not_found(
    client: AsyncClient, salon, tenant_factory, business_factory
):
    stranger = await business_factory(await tenant_factory())
    response = await client.get(url(salon, "overview"), params={"business_id": str(stranger.id)})
    assert response.status_code == 404


async def test_booking_facts_never_cross_tenants(
    db_session: AsyncSession, salon, tenant_factory, as_owner
):
    await add_bookings(db_session, salon, count=3, status=BookingStatus.COMPLETED)
    now = datetime.now(UTC)
    window = TimeRange(starts_at=now - timedelta(days=60), ends_at=now + timedelta(days=1))

    own = BookingRepository(db_session, salon["tenant"].id)
    other = BookingRepository(db_session, (await tenant_factory()).id)

    # As the owner, which RLS does not restrict, so the repository's own
    # filter is all that keeps the other tenant out.
    async with as_owner():
        mine = await own.list_facts(business_id=salon["business"].id, window=window, limit=100)
        theirs = await other.list_facts(business_id=salon["business"].id, window=window, limit=100)

    assert len(mine) == 3
    assert theirs == []
