"""Queue router: what a joining customer is told, and what reception sees and does."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import Principal, PrincipalKind, get_principal
from app.db.outbox import OutboxEvent
from app.db.session import set_tenant_scope
from app.modules.booking.models import BookingRecord


async def test_wait_estimate_counts_every_active_provider_at_the_branch(
    client,
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
    service = await service_factory(location)
    for _ in range(3):
        await provider_factory(location)
    # A provider who is switched off is not cutting anyone's hair.
    await provider_factory(location, is_active=False)

    base = f"/api/v1/tenants/{tenant.id}"
    queue = (
        await client.post(
            f"{base}/queues",
            json={"location_id": str(location.id), "average_service_minutes": 30},
        )
    ).json()

    joined = []
    for _ in range(4):
        customer = await customer_factory(tenant)
        response = await client.post(
            f"{base}/queues/{queue['id']}/entries",
            json={"service_id": str(service.id), "on_behalf_of_customer_id": str(customer.id)},
        )
        assert response.status_code == 201
        joined.append(response.json())

    # Three ahead, three chairs working: one round of 30 minutes, not three.
    assert joined[3]["place_in_line"] == 4
    assert joined[3]["estimated_wait_minutes"] == 30


async def test_joined_event_carries_the_place_in_line(
    client,
    db_session,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    customer_factory,
):
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    location = await location_factory(business)
    service = await service_factory(location)

    base = f"/api/v1/tenants/{tenant.id}"
    queue = (await client.post(f"{base}/queues", json={"location_id": str(location.id)})).json()
    for _ in range(2):
        customer = await customer_factory(tenant)
        response = await client.post(
            f"{base}/queues/{queue['id']}/entries",
            json={"service_id": str(service.id), "on_behalf_of_customer_id": str(customer.id)},
        )
        assert response.status_code == 201

    events = (
        (
            await db_session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.tenant_id == tenant.id)
                .where(OutboxEvent.event_name == "QueueEntryJoined")
            )
        )
        .scalars()
        .all()
    )

    # The WhatsApp "you're in line" message reads this; it used to be blank.
    assert sorted(e.payload["place_in_line"] for e in events) == [1, 2]


# --- the reception board ---------------------------------------------------


@pytest.fixture
async def line(
    client, tenant_factory, business_factory, location_factory, service_factory, customer_factory
):
    """A branch with an open queue and a helper that adds a named walk-in."""
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    location = await location_factory(business)
    service = await service_factory(location)
    base = f"/api/v1/tenants/{tenant.id}"
    queue = (await client.post(f"{base}/queues", json={"location_id": str(location.id)})).json()

    async def add(full_name: str = "Walk In") -> dict:
        customer = await customer_factory(tenant, full_name=full_name)
        response = await client.post(
            f"{base}/queues/{queue['id']}/entries",
            json={"service_id": str(service.id), "on_behalf_of_customer_id": str(customer.id)},
        )
        assert response.status_code == 201, response.text
        return response.json()

    return SimpleNamespace(
        tenant=tenant, location=location, service=service, base=base, queue=queue, add=add
    )


async def _board(client, line) -> list[dict]:
    response = await client.get(f"{line.base}/queues/{line.queue['id']}/entries")
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def test_staff_check_in_a_called_walk_in_without_a_ticket(client, line):
    entry = await line.add()
    called = await client.post(f"{line.base}/queues/{line.queue['id']}/call-next")
    assert called.json()["id"] == entry["id"]

    response = await client.post(f"{line.base}/queues/entries/{entry['id']}/check-in")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "checked_in"


async def test_a_customer_cannot_check_anyone_in(app, client, line):
    entry = await line.add()
    await client.post(f"{line.base}/queues/{line.queue['id']}/call-next")
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=uuid4(), kind=PrincipalKind.CUSTOMER
    )

    response = await client.post(f"{line.base}/queues/entries/{entry['id']}/check-in")

    assert response.status_code == 403


async def test_a_requeued_customer_goes_behind_someone_who_joined_after_them(client, line):
    first = await line.add()
    await client.post(f"{line.base}/queues/{line.queue['id']}/call-next")
    second = await line.add()

    missed = await client.post(f"{line.base}/queues/entries/{first['id']}/missed")
    assert missed.status_code == 200
    requeued = await client.post(f"{line.base}/queues/entries/{first['id']}/requeue")
    assert requeued.status_code == 200

    called = await client.post(f"{line.base}/queues/{line.queue['id']}/call-next")
    assert called.json()["id"] == second["id"]


async def test_the_board_names_people_and_keeps_the_missed(client, line):
    first = await line.add("Noura")
    await line.add("Reem")
    third = await line.add("Huda")
    await client.post(f"{line.base}/queues/{line.queue['id']}/call-next")
    await client.post(f"{line.base}/queues/entries/{first['id']}/missed")

    board = await _board(client, line)

    assert [e["customer_name"] for e in board] == ["Reem", "Huda", "Noura"]
    # Noura was missed: off the line, so not ahead of anyone, but still listed.
    assert [e["place_in_line"] for e in board] == [1, 2, None]
    assert board[-1]["status"] == "missed"
    assert board[1]["id"] == third["id"]


async def test_a_called_customer_has_no_place_in_line(client, line):
    entry = await line.add()
    await client.post(f"{line.base}/queues/{line.queue['id']}/call-next")

    response = await client.get(f"{line.base}/queues/entries/{entry['id']}")

    assert response.json()["place_in_line"] is None
    assert response.json()["estimated_wait_minutes"] is None


async def test_a_closed_queue_still_serves_the_people_waiting(client, line):
    entry = await line.add()
    closed = await client.patch(
        f"{line.base}/queues/{line.queue['id']}/open", json={"is_open": False}
    )
    assert closed.status_code == 200

    response = await client.post(f"{line.base}/queues/{line.queue['id']}/call-next")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == entry["id"]


async def test_a_missed_customer_can_be_removed(client, line):
    entry = await line.add()
    await client.post(f"{line.base}/queues/{line.queue['id']}/call-next")
    await client.post(f"{line.base}/queues/entries/{entry['id']}/missed")

    response = await client.post(f"{line.base}/queues/entries/{entry['id']}/cancel")

    assert response.status_code == 200, response.text
    assert await _board(client, line) == []


# --- arriving appointments ---------------------------------------------------


async def _booking(db_session, line, provider, customer, **overrides) -> BookingRecord:
    starts_at = datetime.now(UTC) + timedelta(minutes=10)
    record = BookingRecord(
        tenant_id=line.tenant.id,
        business_id=line.location.business_id,
        location_id=line.location.id,
        service_id=line.service.id,
        provider_id=provider.id,
        customer_id=customer.id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        price=Decimal("150.00"),
        currency="SAR",
        status="confirmed",
        source="direct_link",
    )
    for key, value in overrides.items():
        setattr(record, key, value)
    await set_tenant_scope(db_session, line.tenant.id)
    db_session.add(record)
    await db_session.flush()
    return record


async def test_an_arriving_appointment_joins_with_its_bookings_service(
    client, db_session, line, provider_factory, customer_factory
):
    provider = await provider_factory(line.location)
    customer = await customer_factory(line.tenant)
    booking = await _booking(db_session, line, provider, customer)

    response = await client.post(
        f"{line.base}/queues/{line.queue['id']}/entries",
        json={"booking_id": str(booking.id), "on_behalf_of_customer_id": str(customer.id)},
    )

    assert response.status_code == 201, response.text
    assert response.json()["source"] == "appointment"
    assert response.json()["service_id"] == str(line.service.id)


async def test_someone_elses_booking_does_not_jump_the_line(
    client, db_session, line, provider_factory, customer_factory
):
    provider = await provider_factory(line.location)
    owner, stranger = await customer_factory(line.tenant), await customer_factory(line.tenant)
    booking = await _booking(db_session, line, provider, owner)

    response = await client.post(
        f"{line.base}/queues/{line.queue['id']}/entries",
        json={
            "service_id": str(line.service.id),
            "booking_id": str(booking.id),
            "on_behalf_of_customer_id": str(stranger.id),
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "booking_not_found"


async def test_a_cancelled_booking_does_not_jump_the_line(
    client, db_session, line, provider_factory, customer_factory
):
    provider = await provider_factory(line.location)
    customer = await customer_factory(line.tenant)
    booking = await _booking(db_session, line, provider, customer, status="cancelled")

    response = await client.post(
        f"{line.base}/queues/{line.queue['id']}/entries",
        json={"booking_id": str(booking.id), "on_behalf_of_customer_id": str(customer.id)},
    )

    assert response.status_code == 404
