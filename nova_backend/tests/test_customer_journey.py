"""The journey docs/09 describes, exercised end to end through the API.

Acceptance criteria covered here:

    #1  a business owner can create a business and location
    #2  services, providers and schedules can be added
    #3  a customer can DISCOVER a business and book a service
    #4  availability is deterministic and prevents double booking
    #6  a virtual ticket with a secure QR code is generated
    #7  walk-ins and appointments coexist in the queue
    #8  reception can scan QR tickets and check customers in

Real HTTP through the real routers against a real Postgres. These are the tests
that would have caught every wiring mistake the unit tests cannot see.
"""

from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.anyio if False else []


async def _monday_at(hour_local: int) -> datetime:
    """A future Monday at a Riyadh wall-clock hour, as UTC."""
    base = datetime.now(UTC) + timedelta(days=7)
    monday = base + timedelta(days=(7 - base.weekday()) % 7 or 7)
    return monday.replace(hour=hour_local - 3, minute=0, second=0, microsecond=0)


async def test_owner_sets_up_a_branch_and_a_customer_books_it(
    client, tenant_factory, business_factory, location_factory, customer_factory
):
    """docs/09 #1, #2, #3 — setup through to a booked appointment."""
    tenant = await tenant_factory()
    base = f"/api/v1/tenants/{tenant.id}"

    # A business and a branch (#1).
    business = (
        await client.post(
            f"{base}/catalog/businesses",
            json={"name_en": "Glow Studio", "name_ar": "استوديو جلو"},
        )
    ).json()

    location = (
        await client.post(
            f"{base}/catalog/locations",
            json={
                "business_id": business["id"],
                "name_en": "Olaya Branch",
                "name_ar": "فرع العليا",
                "phone": "+966500000001",
                "timezone": "Asia/Riyadh",
            },
        )
    ).json()

    # A service and a provider, and the provider qualified for it (#2).
    service = (
        await client.post(
            f"{base}/catalog/services",
            json={
                "location_id": location["id"],
                "name_en": "Haircut",
                "name_ar": "قص شعر",
                "duration_minutes": 60,
                "price": "150.00",
            },
        )
    ).json()

    provider = (
        await client.post(
            f"{base}/catalog/providers",
            json={
                "location_id": location["id"],
                "name_en": "Sara",
                "name_ar": "سارة",
            },
        )
    ).json()

    assigned = await client.post(
        f"{base}/catalog/providers/{provider['id']}/services",
        json={"service_id": service["id"]},
    )
    assert assigned.status_code == 204

    # Working hours: Monday 09:00-17:00 local (#2, the `Schedule` aggregate).
    schedule = await client.put(
        f"{base}/schedules/providers/{provider['id']}",
        json={"windows": [{"weekday": 0, "start_minute": 540, "end_minute": 1020}]},
    )
    assert schedule.status_code == 200
    assert len(schedule.json()["windows"]) == 1

    # Availability is generated from that schedule (#4).
    monday = await _monday_at(9)
    availability = await client.get(
        f"{base}/bookings/availability",
        params={
            "provider_id": provider["id"],
            "service_id": service["id"],
            "date_from": monday.isoformat(),
            "date_to": (monday + timedelta(days=1)).isoformat(),
        },
    )
    assert availability.status_code == 200
    slots = availability.json()["items"]
    assert slots, "the provider works on Monday, so there must be slots"
    # Every slot carries a signed id (docs/07 section 5).
    assert all(slot["slot_id"] for slot in slots)

    # The customer books one of them (#3).
    customer = await customer_factory(tenant)
    created = await client.post(
        f"{base}/bookings",
        json={
            "location_id": location["id"],
            "service_id": service["id"],
            "provider_id": provider["id"],
            "starts_at": slots[0]["starts_at"],
            "slot_id": slots[0]["slot_id"],
            "on_behalf_of_customer_id": str(customer.id),
        },
    )
    assert created.status_code == 201, created.text
    booking = created.json()
    assert booking["status"] == "draft"
    # Price and duration come from the catalog, never the client.
    assert booking["price"] == "150.00"

    # That time is no longer offered (#4).
    after = await client.get(
        f"{base}/bookings/availability",
        params={
            "provider_id": provider["id"],
            "service_id": service["id"],
            "date_from": monday.isoformat(),
            "date_to": (monday + timedelta(days=1)).isoformat(),
        },
    )
    assert slots[0]["starts_at"] not in [s["starts_at"] for s in after.json()["items"]]


async def test_the_same_slot_cannot_be_booked_twice(
    client,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
    customer_factory,
):
    """docs/09 #4 — the rule the whole product rests on."""
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    location = await location_factory(business)
    service = await service_factory(location)
    provider = await provider_factory(location)
    await qualify(provider, service)
    first_customer = await customer_factory(tenant)
    second_customer = await customer_factory(tenant)

    base = f"/api/v1/tenants/{tenant.id}"
    starts_at = (datetime.now(UTC) + timedelta(days=3)).replace(microsecond=0)

    payload = {
        "location_id": str(location.id),
        "service_id": str(service.id),
        "provider_id": str(provider.id),
        "starts_at": starts_at.isoformat(),
    }

    first = await client.post(
        f"{base}/bookings", json={**payload, "on_behalf_of_customer_id": str(first_customer.id)}
    )
    assert first.status_code == 201

    # A different customer, same provider, same time.
    second = await client.post(
        f"{base}/bookings", json={**payload, "on_behalf_of_customer_id": str(second_customer.id)}
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "slot_unavailable"
    # 409s are worth retrying at a different time, and say so.
    assert second.json()["error"]["retryable"] is True


async def test_a_retried_booking_does_not_create_two_appointments(
    client,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
    customer_factory,
):
    """An `Idempotency-Key` replay returns the first booking, not a second one."""
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    location = await location_factory(business)
    service = await service_factory(location)
    provider = await provider_factory(location)
    await qualify(provider, service)
    customer = await customer_factory(tenant)

    base = f"/api/v1/tenants/{tenant.id}"
    payload = {
        "location_id": str(location.id),
        "service_id": str(service.id),
        "provider_id": str(provider.id),
        "starts_at": (datetime.now(UTC) + timedelta(days=4)).replace(microsecond=0).isoformat(),
        "on_behalf_of_customer_id": str(customer.id),
    }
    headers = {"Idempotency-Key": "tap-happened-twice"}

    first = await client.post(f"{base}/bookings", json=payload, headers=headers)
    second = await client.post(f"{base}/bookings", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    # The same booking, not a second one at the same time.
    assert first.json()["id"] == second.json()["id"]
    assert second.headers.get("Idempotent-Replay") == "true"


async def test_reusing_a_key_with_a_different_body_is_rejected(
    client,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
    customer_factory,
):
    """Silently serving the first response would hide a client bug."""
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    location = await location_factory(business)
    service = await service_factory(location)
    provider = await provider_factory(location)
    await qualify(provider, service)
    customer = await customer_factory(tenant)

    base = f"/api/v1/tenants/{tenant.id}"
    headers = {"Idempotency-Key": "reused"}
    payload = {
        "location_id": str(location.id),
        "service_id": str(service.id),
        "provider_id": str(provider.id),
        "starts_at": (datetime.now(UTC) + timedelta(days=5)).replace(microsecond=0).isoformat(),
        "on_behalf_of_customer_id": str(customer.id),
    }

    assert (await client.post(f"{base}/bookings", json=payload, headers=headers)).status_code == 201

    changed = {
        **payload,
        "starts_at": (datetime.now(UTC) + timedelta(days=6)).replace(microsecond=0).isoformat(),
    }
    reused = await client.post(f"{base}/bookings", json=changed, headers=headers)
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "idempotency_key_reused"


async def test_a_held_slot_is_not_offered_to_anyone_else(
    client,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
):
    """docs/04 section 2A — without this, two customers reach checkout for one slot."""
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    location = await location_factory(business)
    service = await service_factory(location)
    provider = await provider_factory(location)
    await qualify(provider, service)

    base = f"/api/v1/tenants/{tenant.id}"
    starts_at = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)

    held = await client.post(
        f"{base}/bookings/holds",
        json={
            "provider_id": str(provider.id),
            "service_id": str(service.id),
            "starts_at": starts_at.isoformat(),
        },
    )
    assert held.status_code == 201
    assert held.json()["hold_token"]

    # A second hold on the same slot loses.
    again = await client.post(
        f"{base}/bookings/holds",
        json={
            "provider_id": str(provider.id),
            "service_id": str(service.id),
            "starts_at": starts_at.isoformat(),
        },
    )
    assert again.status_code == 409

    # Releasing it puts the slot back.
    released = await client.delete(f"{base}/bookings/holds/{held.json()['hold_token']}")
    assert released.status_code == 204

    third = await client.post(
        f"{base}/bookings/holds",
        json={
            "provider_id": str(provider.id),
            "service_id": str(service.id),
            "starts_at": starts_at.isoformat(),
        },
    )
    assert third.status_code == 201


async def test_walk_ins_and_appointments_share_one_queue_and_check_in_by_qr(
    client,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
    customer_factory,
):
    """docs/09 #6, #7, #8 — the queue and QR check-in journey."""
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    location = await location_factory(business)
    service = await service_factory(location)
    provider = await provider_factory(location)
    await qualify(provider, service)
    walk_in = await customer_factory(tenant)
    booked = await customer_factory(tenant)

    base = f"/api/v1/tenants/{tenant.id}"

    queue = (await client.post(f"{base}/queues", json={"location_id": str(location.id)})).json()

    # A walk-in joins.
    walk_in_entry = await client.post(
        f"{base}/queues/{queue['id']}/entries",
        json={
            "service_id": str(service.id),
            "on_behalf_of_customer_id": str(walk_in.id),
        },
    )
    assert walk_in_entry.status_code == 201
    assert walk_in_entry.json()["source"] == "walk_in"
    assert walk_in_entry.json()["place_in_line"] == 1

    # An appointment arrives and joins the SAME queue (#7).
    booking = (
        await client.post(
            f"{base}/bookings",
            json={
                "location_id": str(location.id),
                "service_id": str(service.id),
                "provider_id": str(provider.id),
                "starts_at": (datetime.now(UTC) + timedelta(days=1))
                .replace(microsecond=0)
                .isoformat(),
                "on_behalf_of_customer_id": str(booked.id),
            },
        )
    ).json()

    appointment_entry = await client.post(
        f"{base}/queues/{queue['id']}/entries",
        json={
            "service_id": str(service.id),
            "booking_id": booking["id"],
            "on_behalf_of_customer_id": str(booked.id),
        },
    )
    assert appointment_entry.status_code == 201
    assert appointment_entry.json()["source"] == "appointment"

    listed = await client.get(f"{base}/queues/{queue['id']}/entries")
    assert listed.json()["total"] == 2

    # The same person cannot occupy two places.
    duplicate = await client.post(
        f"{base}/queues/{queue['id']}/entries",
        json={"service_id": str(service.id), "on_behalf_of_customer_id": str(walk_in.id)},
    )
    assert duplicate.status_code == 409

    # A ticket is issued for the queue entry (#6).
    ticket = await client.post(
        f"{base}/tickets", json={"queue_entry_id": walk_in_entry.json()["id"]}
    )
    assert ticket.status_code == 201
    payload = ticket.json()
    assert payload["qr_payload"].count(".") == 2
    assert payload["ticket_page_url"].endswith(payload["ticket_code"])
    # No PII in the QR payload (docs/06 section 6).
    assert walk_in.phone not in payload["qr_payload"]
    assert walk_in.full_name not in payload["qr_payload"]

    # Reception calls the next person, then scans them in (#8).
    called = await client.post(f"{base}/queues/{queue['id']}/call-next")
    assert called.status_code == 200

    scanned = await client.post(
        f"{base}/tickets/check-in", json={"qr_payload": payload["qr_payload"]}
    )
    assert scanned.status_code == 200
    assert scanned.json()["ticket"]["status"] == "redeemed"
    assert scanned.json()["entry"]["status"] == "checked_in"

    # Scanning again returns the same result rather than erroring at a busy
    # reception desk (docs/08 section 13: redemption is idempotent).
    rescanned = await client.post(
        f"{base}/tickets/check-in", json={"qr_payload": payload["qr_payload"]}
    )
    assert rescanned.status_code == 200
    assert rescanned.json()["ticket"]["status"] == "redeemed"


async def test_a_forged_qr_code_is_refused(
    client,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    customer_factory,
):
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    location = await location_factory(business)
    await service_factory(location)

    base = f"/api/v1/tenants/{tenant.id}"
    forged = await client.post(
        f"{base}/tickets/check-in",
        json={"qr_payload": "00000000-0000-0000-0000-000000000001.token.deadbeef"},
    )
    assert forged.status_code == 422
    assert forged.json()["error"]["code"] == "ticket_invalid"


async def test_a_customer_discovers_a_salon_and_books_it_knowing_nothing_first(
    client,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
    customer_factory,
):
    """docs/09 #3, whole. The journey no other test could start.

    Every other test in this file begins by already holding a `tenant_id`,
    which is exactly what a customer discovering a salon does not have. This
    one starts from a search box and nothing else, and the tenant, business,
    location, service, provider and slot are all *found* rather than supplied.
    """
    tenant = await tenant_factory()
    business = await business_factory(
        tenant, name_en="Discoverable Studio", slug="discoverable-studio"
    )
    location = await location_factory(business, city="Riyadh")
    service = await service_factory(location, name_en="Haircut")
    provider = await provider_factory(location)
    await qualify(provider, service)

    await client.put(
        f"/api/v1/tenants/{tenant.id}/schedules/providers/{provider.id}",
        json={"windows": [{"weekday": 0, "start_minute": 540, "end_minute": 1020}]},
    )

    # 1. A search box. No tenant, no account, no ids.
    results = await client.get(
        "/api/v1/discovery/businesses", params={"q": "Haircut", "city": "Riyadh"}
    )
    assert results.status_code == 200
    card = next(item for item in results.json()["items"] if item["slug"] == "discoverable-studio")
    assert card["starting_price"] == "150.00"

    # 2. Open the storefront by its public slug.
    storefront = await client.get(f"/api/v1/discovery/businesses/{card['slug']}")
    assert storefront.status_code == 200
    found = storefront.json()
    found_service = found["services"][0]
    # This is where the customer learns the tenant they are dealing with.
    assert found["tenant_id"] == str(tenant.id)

    # 3. Real times, still anonymous.
    monday = await _monday_at(9)
    availability = await client.get(
        f"/api/v1/discovery/businesses/{card['slug']}/services/{found_service['id']}/availability",
        params={
            "date_from": monday.isoformat(),
            "date_to": (monday + timedelta(days=1)).isoformat(),
        },
    )
    assert availability.status_code == 200
    slots = availability.json()["slots"]
    assert slots, "the provider works on Monday"

    # 4. Book the slot that was discovered, using only what discovery returned.
    customer = await customer_factory(tenant)
    chosen = slots[0]
    booked = await client.post(
        f"/api/v1/tenants/{found['tenant_id']}/bookings",
        json={
            "location_id": chosen["location_id"],
            "service_id": chosen["service_id"],
            "provider_id": chosen["provider_id"],
            "starts_at": chosen["starts_at"],
            # The signed id from the anonymous availability response verifies,
            # which is what proves the two surfaces issue the same slots.
            "slot_id": chosen["slot_id"],
            "on_behalf_of_customer_id": str(customer.id),
        },
    )

    assert booked.status_code == 201, booked.text
    assert booked.json()["price"] == "150.00"

    # 5. That time is gone from the public listing too, not just the private one.
    after = await client.get(
        f"/api/v1/discovery/businesses/{card['slug']}/services/{found_service['id']}/availability",
        params={
            "date_from": monday.isoformat(),
            "date_to": (monday + timedelta(days=1)).isoformat(),
        },
    )
    assert chosen["starts_at"] not in [s["starts_at"] for s in after.json()["slots"]]
