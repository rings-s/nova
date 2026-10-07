"""Free times for a service across its providers: the one merge the AI tools
and the marketplace both read (`BookingService.availability_for_service`).
Needs Postgres.
"""

from datetime import UTC, datetime, timedelta

from app.db.session import set_tenant_scope
from app.modules.booking.dependencies import build_booking_service
from app.modules.booking.domain import WorkingWindow

#: Every provider works around the clock, so only the rules under test decide.
ALL_WEEK = [WorkingWindow(weekday=day, start_minute=0, end_minute=24 * 60) for day in range(7)]


async def _salon(
    db_session,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
):
    tenant = await tenant_factory()
    location = await location_factory(await business_factory(tenant))
    service = await service_factory(location)
    sara = await provider_factory(location, name_en="Sara")
    huda = await provider_factory(location, name_en="Huda")
    resting = await provider_factory(location, name_en="Rest", is_active=False)
    unqualified = await provider_factory(location, name_en="Noor")
    for provider in (sara, huda, resting):
        await qualify(provider, service)
    await set_tenant_scope(db_session, tenant.id)
    bookings = build_booking_service(db_session, tenant.id)
    for provider in (sara, huda, resting, unqualified):
        await bookings.set_provider_schedule(provider_id=provider.id, windows=ALL_WEEK)
    return tenant, service, (sara, huda, resting, unqualified)


async def test_merges_active_qualified_providers_in_time_order(
    db_session,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
):
    tenant, service, (sara, huda, _resting, _unqualified) = await _salon(
        db_session,
        tenant_factory,
        business_factory,
        location_factory,
        service_factory,
        provider_factory,
        qualify,
    )
    await set_tenant_scope(db_session, tenant.id)
    now = datetime.now(UTC)

    slots = await build_booking_service(db_session, tenant.id).availability_for_service(
        service_id=service.id, date_from=now, date_to=now + timedelta(days=3), now=now
    )

    offered_by = {slot.provider_id for slot in slots}
    assert offered_by == {sara.id, huda.id}
    assert [(s.starts_at, str(s.provider_id)) for s in slots] == sorted(
        (s.starts_at, str(s.provider_id)) for s in slots
    )


async def test_narrows_to_the_callers_providers_and_honours_lead_time(
    db_session,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
):
    tenant, service, (_sara, huda, *_) = await _salon(
        db_session,
        tenant_factory,
        business_factory,
        location_factory,
        service_factory,
        provider_factory,
        qualify,
    )
    await set_tenant_scope(db_session, tenant.id)
    bookings = build_booking_service(db_session, tenant.id)
    now = datetime.now(UTC)

    slots = await bookings.availability_for_service(
        service_id=service.id,
        date_from=now,
        date_to=now + timedelta(days=3),
        provider_ids=[huda.id],
        now=now,
        lead_time_minutes=24 * 60,
    )

    assert slots, "expected free times for Huda after the lead time"
    assert {slot.provider_id for slot in slots} == {huda.id}
    assert min(slot.starts_at for slot in slots) >= now + timedelta(hours=24)
