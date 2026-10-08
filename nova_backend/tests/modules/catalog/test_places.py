"""Filling the branch form from the map: what a pin is called, and two branches
that end up with the same name. Needs Postgres (the client and the slug check).
"""

from fastapi import FastAPI
from httpx import AsyncClient

from app.integrations.geocoding import GeocodingUnavailableError, Place
from app.modules.catalog.dependencies import get_geocoder

#: Al Olaya, Riyadh.
LAT, LNG = 24.6905, 46.6853


class FakeGeocoder:
    def __init__(self, place: Place | None = None) -> None:
        self.place = place
        self.asked: list[tuple[float, float]] = []

    async def reverse(self, *, latitude: float, longitude: float) -> Place:
        self.asked.append((latitude, longitude))
        if self.place is None:
            raise GeocodingUnavailableError()
        return self.place


OLAYA = Place(city_en="Riyadh", city_ar="الرياض", district_en="Al Olaya", district_ar="العليا")


def _reverse(tenant) -> str:
    return f"/api/v1/tenants/{tenant.id}/catalog/places/reverse"


async def test_a_pin_names_the_branch_and_its_city(
    app: FastAPI, client: AsyncClient, tenant_factory
) -> None:
    tenant = await tenant_factory()
    geocoder = FakeGeocoder(OLAYA)
    app.dependency_overrides[get_geocoder] = lambda: geocoder

    response = await client.get(_reverse(tenant), params={"latitude": LAT, "longitude": LNG})

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name_en"], body["name_ar"]) == ("Al Olaya branch", "فرع العليا")
    assert (body["city_en"], body["city_ar"]) == ("Riyadh", "الرياض")
    assert geocoder.asked == [(LAT, LNG)]


async def test_without_a_district_the_city_names_the_branch(
    app: FastAPI, client: AsyncClient, tenant_factory
) -> None:
    tenant = await tenant_factory()
    app.dependency_overrides[get_geocoder] = lambda: FakeGeocoder(
        Place(city_en="Jeddah", city_ar="جدة", district_en=None, district_ar=None)
    )

    body = (await client.get(_reverse(tenant), params={"latitude": 21.5, "longitude": 39.2})).json()

    assert (body["name_en"], body["name_ar"]) == ("Jeddah branch", "فرع جدة")


async def test_a_silent_map_service_is_a_retryable_503(
    app: FastAPI, client: AsyncClient, tenant_factory
) -> None:
    tenant = await tenant_factory()
    app.dependency_overrides[get_geocoder] = lambda: FakeGeocoder(None)

    response = await client.get(_reverse(tenant), params={"latitude": LAT, "longitude": LNG})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "geocoding_unavailable"
    assert response.json()["error"]["retryable"] is True


async def test_a_position_off_the_globe_is_refused(
    app: FastAPI, client: AsyncClient, tenant_factory
) -> None:
    tenant = await tenant_factory()
    app.dependency_overrides[get_geocoder] = lambda: FakeGeocoder(OLAYA)

    response = await client.get(_reverse(tenant), params={"latitude": 91, "longitude": LNG})

    assert response.status_code == 422


async def test_two_branches_in_the_same_district_both_get_created(
    client: AsyncClient, tenant_factory, business_factory
) -> None:
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    body = {
        "business_id": str(business.id),
        "name_en": "Al Olaya branch",
        "name_ar": "فرع العليا",
        "latitude": LAT,
        "longitude": LNG,
    }
    url = f"/api/v1/tenants/{tenant.id}/catalog/locations"

    first = await client.post(url, json=body)
    second = await client.post(url, json=body)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert (first.json()["slug"], second.json()["slug"]) == (
        "al-olaya-branch",
        "al-olaya-branch-2",
    )
