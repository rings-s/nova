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

from app.core.values import TimeRange
from app.db.session import set_tenant_scope
from app.modules.booking.domain import BookingStatus
from app.modules.booking.models import BookingRecord
from app.modules.booking.repository import BookingRepository


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


async def test_conflict_search_sees_a_long_running_booking_and_ignores_ancient_ones(
    db_session, setup
) -> None:
    """The overlap queries bound their scan by `MAX_BOOKING_SPAN`; that bound must
    not hide a booking that is still running, nor drag history back in."""
    tenant, *_, provider, _customer = setup
    now = datetime.now(UTC) + timedelta(days=3)
    # Eight hours long, the longest a service can be, and still running.
    long_one = _booking(setup, now - timedelta(hours=7), BookingStatus.CONFIRMED)
    long_one.ends_at = now + timedelta(hours=1)
    ancient = _booking(setup, now - timedelta(days=200), BookingStatus.COMPLETED)
    db_session.add_all([long_one, ancient])
    await db_session.flush()

    repo = BookingRepository(db_session, tenant.id)
    probe = TimeRange(starts_at=now, ends_at=now + timedelta(minutes=30))
    found = await repo.find_conflicting(provider_id=provider.id, slot=probe)

    assert found is not None
    assert found.id == long_one.id
