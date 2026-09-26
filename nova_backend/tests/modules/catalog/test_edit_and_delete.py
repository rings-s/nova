"""The business edits and deletes what it set up: branches, services,
providers and photos.

Deleting is soft (a past booking must still resolve the service it used) and
is refused while an appointment is still to come, so no confirmed customer is
left booked into something the salon no longer offers.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.db.session import set_tenant_scope
from app.modules.booking.domain import BookingSource, BookingStatus
from app.modules.booking.models import BookingRecord


def _catalog(tenant) -> str:
    return f"/api/v1/tenants/{tenant.id}/catalog"


@pytest.fixture
def salon(
    tenant_factory, business_factory, location_factory, service_factory, provider_factory, qualify
):
    async def _make():
        tenant = await tenant_factory()
        business = await business_factory(tenant)
        location = await location_factory(business)
        service = await service_factory(location)
        provider = await provider_factory(location)
        await qualify(provider, service)
        return tenant, business, location, service, provider

    return _make


async def _book(
    db_session,
    customer_factory,
    tenant,
    business,
    location,
    service,
    provider,
    *,
    starts_in: timedelta,
    status: BookingStatus = BookingStatus.CONFIRMED,
):
    customer = await customer_factory(tenant)
    await set_tenant_scope(db_session, tenant.id)
    starts = datetime.now(UTC) + starts_in
    db_session.add(
        BookingRecord(
            tenant_id=tenant.id,
            business_id=business.id,
            location_id=location.id,
            service_id=service.id,
            provider_id=provider.id,
            customer_id=customer.id,
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            price=Decimal("150.00"),
            currency="SAR",
            status=status,
            source=BookingSource.DIRECT_LINK,
        )
    )
    await db_session.flush()


# --- edit ----------------------------------------------------------------


async def test_a_branch_is_renamed_and_only_what_was_sent_changes(
    client: AsyncClient, salon
) -> None:
    tenant, _, location, _, _ = await salon()

    response = await client.patch(
        f"{_catalog(tenant)}/locations/{location.id}", json={"name_en": "Olaya", "city": "Riyadh"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name_en"], body["city"], body["name_ar"]) == ("Olaya", "Riyadh", location.name_ar)


async def test_a_branch_refuses_an_unknown_timezone(client: AsyncClient, salon) -> None:
    tenant, _, location, _, _ = await salon()

    response = await client.patch(
        f"{_catalog(tenant)}/locations/{location.id}", json={"timezone": "Mars/Olympus"}
    )

    assert response.status_code == 422


async def test_a_service_changes_price_duration_and_category(
    client: AsyncClient, salon, category_factory
) -> None:
    tenant, _, _, service, _ = await salon()
    category = await category_factory()

    response = await client.patch(
        f"{_catalog(tenant)}/services/{service.id}",
        json={"price": "199.00", "duration_minutes": 45, "category_id": str(category.id)},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["price"], body["duration_minutes"]) == ("199.00", 45)
    assert body["category"]["id"] == str(category.id)

    cleared = await client.patch(
        f"{_catalog(tenant)}/services/{service.id}", json={"category_id": None, "price": None}
    )
    # `null` clears the category; a price cannot be nothing, so it is left alone.
    assert (cleared.json()["category"], cleared.json()["price"]) == (None, "199.00")


async def test_a_service_cannot_be_renamed_to_nothing(client: AsyncClient, salon) -> None:
    tenant, _, _, service, _ = await salon()

    response = await client.patch(
        f"{_catalog(tenant)}/services/{service.id}", json={"name_en": "   "}
    )

    assert response.status_code == 422


async def test_a_provider_is_renamed_and_taken_off_the_booking_list(
    client: AsyncClient, salon
) -> None:
    tenant, _, _, _, provider = await salon()

    response = await client.patch(
        f"{_catalog(tenant)}/providers/{provider.id}",
        json={"name_en": "Sara K.", "title_en": "Senior stylist", "is_active": False},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name_en"], body["title_en"], body["is_active"]) == (
        "Sara K.",
        "Senior stylist",
        False,
    )


# --- delete --------------------------------------------------------------


async def test_a_deleted_service_leaves_the_list(client: AsyncClient, salon) -> None:
    tenant, _, location, service, _ = await salon()

    response = await client.delete(f"{_catalog(tenant)}/services/{service.id}")

    assert response.status_code == 204
    listed = (await client.get(f"{_catalog(tenant)}/locations/{location.id}/services")).json()
    assert listed["items"] == []


async def test_deleting_a_branch_retires_its_services_and_providers(
    client: AsyncClient, salon
) -> None:
    tenant, business, location, service, provider = await salon()

    assert (await client.delete(f"{_catalog(tenant)}/locations/{location.id}")).status_code == 204

    branches = (await client.get(f"{_catalog(tenant)}/businesses/{business.id}/locations")).json()
    assert branches["items"] == []
    assert (
        await client.patch(f"{_catalog(tenant)}/services/{service.id}", json={"price": "1.00"})
    ).status_code == 404
    assert (
        await client.patch(f"{_catalog(tenant)}/providers/{provider.id}", json={"name_en": "X"})
    ).status_code == 404


@pytest.mark.parametrize("target", ["locations", "services", "providers"])
async def test_nothing_with_an_upcoming_booking_can_be_deleted(
    client: AsyncClient, db_session, salon, customer_factory, target
) -> None:
    tenant, business, location, service, provider = await salon()
    await _book(
        db_session,
        customer_factory,
        tenant,
        business,
        location,
        service,
        provider,
        starts_in=timedelta(days=1),
    )
    target_id = {"locations": location, "services": service, "providers": provider}[target].id

    response = await client.delete(f"{_catalog(tenant)}/{target}/{target_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "catalog_item_in_use"


@pytest.mark.parametrize(
    ("starts_in", "status"),
    [
        (timedelta(days=-2), BookingStatus.COMPLETED),
        (timedelta(days=1), BookingStatus.CANCELLED),
    ],
)
async def test_past_or_cancelled_bookings_do_not_block_a_delete(
    client: AsyncClient, db_session, salon, customer_factory, starts_in, status
) -> None:
    tenant, business, location, service, provider = await salon()
    await _book(
        db_session,
        customer_factory,
        tenant,
        business,
        location,
        service,
        provider,
        starts_in=starts_in,
        status=status,
    )

    response = await client.delete(f"{_catalog(tenant)}/services/{service.id}")

    assert response.status_code == 204
