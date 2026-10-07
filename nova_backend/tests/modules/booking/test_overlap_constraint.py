"""The database itself refuses to double-book a provider.

The advisory lock in `BookingRepository` is the first line; this is the second,
and it only works if the stored status spelling matches the constraint's
predicate (`status IN ('confirmed', ...)`). Enum columns used to store member
names (`CONFIRMED`), which the predicate never matched.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.session import set_tenant_scope
from app.modules.booking.domain import BookingStatus
from app.modules.booking.models import BookingRecord


@pytest.fixture
async def setup(
    db_session,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
    customer_factory,
):
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    location = await location_factory(business)
    service = await service_factory(location)
    provider = await provider_factory(location)
    await qualify(provider, service)
    customer = await customer_factory(tenant)
    await set_tenant_scope(db_session, tenant.id)
    return tenant, business, location, service, provider, customer


def _booking(setup, starts_at: datetime, status: BookingStatus) -> BookingRecord:
    tenant, business, location, service, provider, customer = setup
    return BookingRecord(
        tenant_id=tenant.id,
        business_id=business.id,
        location_id=location.id,
        service_id=service.id,
        provider_id=provider.id,
        customer_id=customer.id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        price=Decimal("100.00"),
        currency="SAR",
        status=status,
        source="direct_link",
    )


async def test_a_status_is_stored_as_its_value(db_session, setup) -> None:
    record = _booking(setup, datetime.now(UTC) + timedelta(days=3), BookingStatus.CONFIRMED)
    db_session.add(record)
    await db_session.flush()

    stored = (
        await db_session.execute(
            text("SELECT status FROM bookings WHERE id = :id"), {"id": record.id}
        )
    ).scalar_one()
    assert stored == "confirmed"


async def test_two_active_bookings_cannot_overlap_for_one_provider(db_session, setup) -> None:
    start = datetime.now(UTC) + timedelta(days=3)
    db_session.add(_booking(setup, start, BookingStatus.CONFIRMED))
    await db_session.flush()

    with pytest.raises(IntegrityError, match="ex_bookings_no_provider_overlap"):
        async with db_session.begin_nested():
            db_session.add(_booking(setup, start + timedelta(minutes=30), BookingStatus.DRAFT))
            await db_session.flush()


async def test_a_cancelled_booking_frees_the_slot(db_session, setup) -> None:
    start = datetime.now(UTC) + timedelta(days=3)
    db_session.add(_booking(setup, start, BookingStatus.CANCELLED))
    await db_session.flush()

    db_session.add(_booking(setup, start, BookingStatus.CONFIRMED))
    await db_session.flush()
