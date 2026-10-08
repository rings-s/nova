"""Reading Nominatim's answer into a city and a district. Pure: no network."""

import httpx
import pytest

from app.integrations.geocoding import GeocodingUnavailableError, NominatimGeocoder, parse_address


def test_a_city_and_its_district():
    assert parse_address({"suburb": "Al Olaya", "city": "Riyadh", "country": "Saudi Arabia"}) == (
        "Riyadh",
        "Al Olaya",
    )


def test_a_town_stands_in_for_a_city():
    assert parse_address({"town": "Al Kharj", "neighbourhood": "Al Khalidiyah"}) == (
        "Al Kharj",
        "Al Khalidiyah",
    )


def test_a_district_that_only_repeats_the_city_is_dropped():
    assert parse_address({"city_district": "Jeddah", "city": "Jeddah"}) == ("Jeddah", None)


def test_nowhere_in_particular():
    assert parse_address({"country": "Saudi Arabia"}) == (None, None)


async def test_both_languages_come_back_together(monkeypatch):
    answers = {
        "en": {"address": {"suburb": "Al Olaya", "city": "Riyadh"}},
        "ar": {"address": {"suburb": "العليا", "city": "الرياض"}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"].startswith("NOVA/")
        return httpx.Response(200, json=answers[request.url.params["accept-language"]])

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs)
    )
    geocoder = NominatimGeocoder(base_url="https://nominatim.test", user_agent="NOVA/1.0 (+t)")

    place = await geocoder.reverse(latitude=24.69, longitude=46.68)

    assert (place.city_en, place.district_en) == ("Riyadh", "Al Olaya")
    assert (place.city_ar, place.district_ar) == ("الرياض", "العليا")


async def test_a_failed_lookup_is_a_retryable_503(monkeypatch):
    transport = httpx.MockTransport(lambda request: httpx.Response(502))
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs)
    )
    geocoder = NominatimGeocoder(base_url="https://nominatim.test", user_agent="NOVA/1.0 (+t)")

    with pytest.raises(GeocodingUnavailableError) as raised:
        await geocoder.reverse(latitude=24.69, longitude=46.68)
    assert raised.value.status_code == 503 and raised.value.retryable
