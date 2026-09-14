"""The public marketplace surface, over real HTTP against a real database.

docs/09 #3, first half: "a customer can discover a business". These are the
tests for the half of that sentence the suite never covered — every existing
journey test starts by already knowing a `tenant_id`, which is precisely what a
customer discovering a salon does not have.

Two properties are load-bearing here and are asserted repeatedly:

  - discovery reads **across** tenants, which nothing else in NOVA does, and
  - it reads **only published rows**, which is what makes that safe.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

DISCOVERY = "/api/v1/discovery"

#: Riyadh and Jeddah, ~845km apart — far enough that no sane radius joins them.
RIYADH = (24.7136, 46.6753)
JEDDAH = (21.4858, 39.1925)


async def test_a_customer_with_no_tenant_finds_a_salon_by_name(
    client, tenant_factory, business_factory, location_factory
):
    """The single thing this module exists for."""
    tenant = await tenant_factory()
    business = await business_factory(tenant, name_en="Glow Studio", slug="glow-studio-search")
    await location_factory(business, city="Riyadh")

    found = await client.get(DISCOVERY + "/businesses", params={"q": "Glow"})

    assert found.status_code == 200
    slugs = [item["slug"] for item in found.json()["items"]]
    assert "glow-studio-search" in slugs


async def test_search_reaches_across_tenants(
    client, tenant_factory, business_factory, location_factory
):
    """The property that separates discovery from every other read in NOVA.

    Two salons, two tenants, no shared anything — and one query returns both.
    A `TenantScopedRepository` structurally cannot do this, which is why
    `PublicCatalogRepository` exists and why it is read-only.
    """
    first = await business_factory(await tenant_factory(), name_en="Marketplace Alpha")
    second = await business_factory(await tenant_factory(), name_en="Marketplace Beta")
    await location_factory(first)
    await location_factory(second)

    items = (await client.get(DISCOVERY + "/businesses", params={"q": "Marketplace"})).json()[
        "items"
    ]

    tenants = {item["tenant_id"] for item in items}
    assert {str(first.tenant_id), str(second.tenant_id)} <= tenants


async def test_a_salon_is_found_by_something_it_sells(
    client, tenant_factory, business_factory, location_factory, service_factory
):
    """ "Haircut" has to find a salon that never says "haircut" in its name.

    This is the EXISTS branch over services. Without it, marketplace search is
    a business-name lookup, which is not what a customer types.
    """
    business = await business_factory(await tenant_factory(), name_en="Bin Salman Beauty House")
    location = await location_factory(business)
    await service_factory(location, name_en="Balayage", category="hair")

    items = (await client.get(DISCOVERY + "/businesses", params={"q": "Balayage"})).json()["items"]

    assert [item["business_id"] for item in items] == [str(business.id)]


async def test_arabic_search_matches_the_arabic_name(
    client, tenant_factory, business_factory, location_factory
):
    """ADR-0004: neither language is the canonical one."""
    business = await business_factory(
        await tenant_factory(), name_en="Lulu Spa", name_ar="سبا لولو"
    )
    await location_factory(business)

    items = (await client.get(DISCOVERY + "/businesses", params={"q": "لولو"})).json()["items"]

    assert [item["business_id"] for item in items] == [str(business.id)]


async def test_a_wildcard_in_the_query_is_treated_as_a_literal(
    client, tenant_factory, business_factory, location_factory
):
    """`%` and `_` are ILIKE wildcards, and a search box is full of them.

    "e%n" is searched for as those three characters. Unescaped it becomes the
    pattern `%e%n%`, which matches "Percent Free Salon" — and matches most of
    the platform besides.
    """
    business = await business_factory(await tenant_factory(), name_en="Percent Free Salon")
    await location_factory(business)

    items = (await client.get(DISCOVERY + "/businesses", params={"q": "e%n"})).json()["items"]

    assert str(business.id) not in [item["business_id"] for item in items]


async def test_a_literal_percent_still_matches_itself(
    client, tenant_factory, business_factory, location_factory
):
    """Escaping must not make a real `%` in a salon's name unfindable."""
    business = await business_factory(await tenant_factory(), name_en="Save 50% Salon")
    await location_factory(business)

    items = (await client.get(DISCOVERY + "/businesses", params={"q": "50%"})).json()["items"]

    assert str(business.id) in [item["business_id"] for item in items]


async def test_city_filters_the_result(client, tenant_factory, business_factory, location_factory):
    tenant = await tenant_factory()
    riyadh = await business_factory(tenant, name_en="Citywide Salon Riyadh")
    jeddah = await business_factory(tenant, name_en="Citywide Salon Jeddah")
    await location_factory(riyadh, city="Riyadh")
    await location_factory(jeddah, city="Jeddah")

    items = (
        await client.get(DISCOVERY + "/businesses", params={"q": "Citywide", "city": "riyadh"})
    ).json()["items"]

    assert [item["business_id"] for item in items] == [str(riyadh.id)]
    assert items[0]["city"] == "Riyadh"


async def test_a_nearby_branch_is_returned_with_its_distance_and_a_far_one_is_not(
    client, tenant_factory, business_factory, location_factory
):
    """The geo path end to end: bounding box in SQL, exact circle in Python."""
    tenant = await tenant_factory()
    near = await business_factory(tenant, name_en="Geo Near")
    far = await business_factory(tenant, name_en="Geo Far")
    await location_factory(near, latitude=RIYADH[0], longitude=RIYADH[1])
    await location_factory(far, latitude=JEDDAH[0], longitude=JEDDAH[1])

    items = (
        await client.get(
            DISCOVERY + "/businesses",
            params={
                "q": "Geo",
                "latitude": RIYADH[0],
                "longitude": RIYADH[1],
                "radius_km": 25,
            },
        )
    ).json()["items"]

    assert [item["business_id"] for item in items] == [str(near.id)]
    assert items[0]["distance_km"] == pytest.approx(0.0, abs=0.1)


async def test_half_a_coordinate_pair_is_refused(client):
    """Silently ignoring it would turn "near me" into a nationwide search."""
    refused = await client.get(DISCOVERY + "/businesses", params={"latitude": 24.7})
    assert refused.status_code == 422


async def test_the_cheapest_service_is_the_price_on_the_card(
    client, tenant_factory, business_factory, location_factory, service_factory
):
    from decimal import Decimal

    business = await business_factory(await tenant_factory(), name_en="Priced Salon")
    location = await location_factory(business)
    await service_factory(location, name_en="Cut", price=Decimal("150.00"))
    await service_factory(location, name_en="Fringe trim", price=Decimal("60.00"))

    items = (await client.get(DISCOVERY + "/businesses", params={"q": "Priced"})).json()["items"]

    assert items[0]["starting_price"] == "60.00"
    assert items[0]["currency"] == "SAR"


async def test_search_results_do_not_leak_phone_numbers(
    client, tenant_factory, business_factory, location_factory
):
    """ADR-0007 found exactly this defect on the old unauthenticated `GET /tenants`.

    A storefront shows a branch's phone — that is the salon's shop window. One
    search returning every phone number on the platform is a scrape.
    """
    business = await business_factory(await tenant_factory(), name_en="Private Number Salon")
    await location_factory(business, phone="+966500009999")

    body = (await client.get(DISCOVERY + "/businesses", params={"q": "Private Number"})).text

    assert "+966500009999" not in body


class TestOnlyPublishedRowsAreVisible:
    """The restriction that makes a cross-tenant read safe.

    Each test changes its flag as the schema owner, not under a tenant scope. A
    test is one transaction, so a scope set here would still be set during the
    discovery request, which would then see the salon through `tenant_isolation`
    instead of being refused it by `public_discovery`.
    """

    async def test_a_delisted_business_vanishes_from_search(
        self, client, tenant_factory, business_factory, location_factory, db_session, as_owner
    ):
        """docs/11 section 8: an invoice 21 days overdue hides the listing."""
        business = await business_factory(await tenant_factory(), name_en="Unpaid Salon")
        await location_factory(business)

        async with as_owner():
            business.is_listed = False
            await db_session.flush()

        items = (await client.get(DISCOVERY + "/businesses", params={"q": "Unpaid"})).json()[
            "items"
        ]
        assert items == []

    async def test_a_delisted_business_has_no_storefront(
        self, client, tenant_factory, business_factory, location_factory, db_session, as_owner
    ):
        business = await business_factory(
            await tenant_factory(), name_en="Hidden Salon", slug="hidden-salon"
        )
        await location_factory(business)
        async with as_owner():
            business.is_listed = False
            await db_session.flush()

        assert (await client.get(f"{DISCOVERY}/businesses/hidden-salon")).status_code == 404

    async def test_an_inactive_business_is_invisible(
        self, client, tenant_factory, business_factory, location_factory, db_session, as_owner
    ):
        business = await business_factory(await tenant_factory(), name_en="Switched Off Salon")
        await location_factory(business)
        async with as_owner():
            business.is_active = False
            await db_session.flush()

        items = (await client.get(DISCOVERY + "/businesses", params={"q": "Switched Off"})).json()
        assert items["items"] == []

    async def test_a_retired_business_is_invisible(
        self, client, tenant_factory, business_factory, location_factory, db_session, as_owner
    ):
        business = await business_factory(await tenant_factory(), name_en="Retired Salon")
        await location_factory(business)
        async with as_owner():
            business.mark_deleted(now=datetime.now(UTC))
            await db_session.flush()

        items = (await client.get(DISCOVERY + "/businesses", params={"q": "Retired"})).json()
        assert items["items"] == []

    async def test_a_retired_service_is_not_on_the_storefront(
        self,
        client,
        tenant_factory,
        business_factory,
        location_factory,
        service_factory,
        db_session,
        as_owner,
    ):
        """A salon that stopped offering a treatment must not still sell it.

        The row survives, because historical bookings reference it — see
        `SoftDeleteMixin`. It just stops being offered.
        """
        business = await business_factory(await tenant_factory(), slug="retired-service-salon")
        location = await location_factory(business)
        live = await service_factory(location, name_en="Still Offered")
        retired = await service_factory(location, name_en="No Longer Offered")
        async with as_owner():
            retired.mark_deleted(now=datetime.now(UTC))
            await db_session.flush()

        storefront = (await client.get(f"{DISCOVERY}/businesses/retired-service-salon")).json()

        offered = {service["id"] for service in storefront["services"]}
        assert str(live.id) in offered
        assert str(retired.id) not in offered

    async def test_an_unknown_slug_is_a_404(self, client):
        assert (await client.get(f"{DISCOVERY}/businesses/no-such-salon")).status_code == 404


async def test_the_storefront_carries_everything_needed_to_choose(
    client,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
):
    """One call, because four round trips is a page filling in piece by piece."""
    tenant = await tenant_factory()
    business = await business_factory(tenant, name_en="Full Storefront", slug="full-storefront")
    location = await location_factory(business, city="Riyadh", phone="+966500001234")
    service = await service_factory(location, name_en="Haircut")
    provider = await provider_factory(location, name_en="Sara")

    storefront = (await client.get(f"{DISCOVERY}/businesses/full-storefront")).json()

    assert storefront["business_id"] == str(business.id)
    # The tenant id is the one field a customer must carry forward: every
    # booking route is nested under it.
    assert storefront["tenant_id"] == str(tenant.id)
    assert [row["id"] for row in storefront["locations"]] == [str(location.id)]
    assert [row["id"] for row in storefront["services"]] == [str(service.id)]
    assert [row["id"] for row in storefront["providers"]] == [str(provider.id)]
    # A storefront does show the branch phone — it is the salon's shop window.
    assert storefront["locations"][0]["phone"] == "+966500001234"


async def test_public_availability_offers_only_qualified_providers(
    client,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
    db_session: AsyncSession,
):
    """The bridge from discovery to booking.

    A customer who has not signed in can still see real times, and the slots
    carry the same signed `slot_id` the authenticated route issues — so the
    slot they picked anonymously is bookable, and the server can still prove it
    offered exactly that slot (docs/07 section 5).
    """
    tenant = await tenant_factory()
    business = await business_factory(tenant, slug="availability-salon")
    location = await location_factory(business)
    service = await service_factory(location)
    qualified = await provider_factory(location, name_en="Qualified Sara")
    await provider_factory(location, name_en="Unqualified Noor")
    await qualify(qualified, service)

    base = f"/api/v1/tenants/{tenant.id}"
    schedule = await client.put(
        f"{base}/schedules/providers/{qualified.id}",
        json={"windows": [{"weekday": 0, "start_minute": 540, "end_minute": 1020}]},
    )
    assert schedule.status_code == 200

    monday = datetime.now(UTC) + timedelta(days=7)
    monday = (monday + timedelta(days=(7 - monday.weekday()) % 7 or 7)).replace(
        hour=6, minute=0, second=0, microsecond=0
    )

    availability = await client.get(
        f"{DISCOVERY}/businesses/availability-salon/services/{service.id}/availability",
        params={
            "date_from": monday.isoformat(),
            "date_to": (monday + timedelta(days=1)).isoformat(),
        },
    )

    assert availability.status_code == 200
    body = availability.json()
    assert body["tenant_id"] == str(tenant.id)
    assert body["price"] == "150.00"
    assert body["slots"], "the qualified provider works on Monday"
    # Only the qualified provider is offered, and every slot is signed.
    assert {slot["provider_id"] for slot in body["slots"]} == {str(qualified.id)}
    assert all(slot["slot_id"] for slot in body["slots"])
    # Chronological across providers, not grouped by stylist.
    starts = [slot["starts_at"] for slot in body["slots"]]
    assert starts == sorted(starts)


async def test_availability_for_a_service_at_another_salon_is_a_404(
    client, tenant_factory, business_factory, location_factory, service_factory
):
    """The slug is not decoration.

    A bare `service_id` on a public route reads any service on the platform by
    guessing a UUID, including one belonging to a de-listed salon.
    """
    tenant = await tenant_factory()
    mine = await business_factory(tenant, slug="my-salon")
    await location_factory(mine)

    theirs = await business_factory(await tenant_factory(), slug="their-salon")
    their_location = await location_factory(theirs)
    their_service = await service_factory(their_location)

    now = datetime.now(UTC)
    mismatched = await client.get(
        f"{DISCOVERY}/businesses/my-salon/services/{their_service.id}/availability",
        params={
            "date_from": now.isoformat(),
            "date_to": (now + timedelta(days=1)).isoformat(),
        },
    )
    assert mismatched.status_code == 404


async def test_an_over_wide_availability_window_is_refused(
    client, tenant_factory, business_factory, location_factory, service_factory
):
    """The public route answers for every qualified provider at once.

    The authenticated route is per provider, so naming one caps its cost. This
    one has no such cap and no principal behind it, so the window is bounded
    instead — a customer picking a time looks at this week, not at ninety days.
    """
    business = await business_factory(await tenant_factory(), slug="wide-window-salon")
    location = await location_factory(business)
    service = await service_factory(location)

    now = datetime.now(UTC)
    too_wide = await client.get(
        f"{DISCOVERY}/businesses/wide-window-salon/services/{service.id}/availability",
        params={
            "date_from": now.isoformat(),
            "date_to": (now + timedelta(days=90)).isoformat(),
        },
    )

    assert too_wide.status_code == 422
    assert "14 days" in too_wide.json()["error"]["message"]


async def test_a_backwards_availability_window_is_refused(
    client, tenant_factory, business_factory, location_factory, service_factory
):
    business = await business_factory(await tenant_factory(), slug="backwards-window-salon")
    location = await location_factory(business)
    service = await service_factory(location)

    now = datetime.now(UTC)
    backwards = await client.get(
        f"{DISCOVERY}/businesses/backwards-window-salon/services/{service.id}/availability",
        params={
            "date_from": now.isoformat(),
            "date_to": (now - timedelta(days=1)).isoformat(),
        },
    )
    assert backwards.status_code == 422
