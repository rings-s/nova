"""A business locked by billing (its free week ended unpaid, or day 21 of
dunning) takes no online bookings from customers; staff can still book a
walk-in for it. Needs Postgres.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.session import set_tenant_scope
from app.modules.booking.dependencies import build_booking_service
from app.modules.booking.domain import WorkingWindow
from app.modules.booking.exceptions import BusinessUnavailableError

ALL_WEEK = [WorkingWindow(weekday=day, start_minute=0, end_minute=24 * 60) for day in range(7)]


async def _locked_salon(
    db_session,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
):
    tenant = await tenant_factory()
    business = await business_factory(tenant, hidden_by_billing=True)
    location = await location_factory(business)
    service = await service_factory(location)
    provider = await provider_factory(location)
    await qualify(provider, service)
    await set_tenant_scope(db_session, tenant.id)
    bookings = build_booking_service(db_session, tenant.id)
    await bookings.set_provider_schedule(provider_id=provider.id, windows=ALL_WEEK)
    return bookings, tenant, location, service, provider


async def test_a_customer_cannot_book_online_at_a_locked_business(
    db_session,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
):
    bookings, _tenant, location, service, provider = await _locked_salon(
        db_session,
        tenant_factory,
        business_factory,
        location_factory,
        service_factory,
        provider_factory,
        qualify,
    )

    with pytest.raises(BusinessUnavailableError):
        await bookings.create(
            location_id=location.id,
            service_id=service.id,
            provider_id=provider.id,
            customer_reference_id=uuid4(),
            self_service=True,
            starts_at=(datetime.now(UTC) + timedelta(days=2)).replace(
                minute=0, second=0, microsecond=0
            ),
        )


async def test_staff_can_still_book_a_walk_in_for_it(
    db_session,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
    customer_factory,
):
    bookings, tenant, location, service, provider = await _locked_salon(
        db_session,
        tenant_factory,
        business_factory,
        location_factory,
        service_factory,
        provider_factory,
        qualify,
    )
    customer = await customer_factory(tenant)

    booking = await bookings.create(
        location_id=location.id,
        service_id=service.id,
        provider_id=provider.id,
        customer_reference_id=customer.id,
        self_service=False,
        starts_at=(datetime.now(UTC) + timedelta(days=2)).replace(
            minute=0, second=0, microsecond=0
        ),
    )

    assert booking.id is not None
