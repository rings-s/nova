"""Reverse geocoding: what a point on the map is called, in English and Arabic.

The branch form fills its names and city from the pin (`GET /catalog/places/
reverse`), so an owner never types an address. OpenStreetMap's Nominatim is the
adapter here, the same map data the tiles come from (ADR-0012). It is called by
the API, never the browser: Nominatim's usage policy wants an identifying
User-Agent and a request rate NOVA controls, and the browser's CSP stays as it is.
"""

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.exceptions import DomainError
from app.integrations.base import IntegrationNotConfiguredError

logger = logging.getLogger(__name__)

#: Nominatim address keys, most specific first, for "which city" and "which
#: district". A village or a town counts as the city where there is no city.
_CITY_KEYS = ("city", "town", "village", "municipality", "county", "state")
_DISTRICT_KEYS = ("suburb", "neighbourhood", "quarter", "city_district", "residential", "road")


class GeocodingUnavailableError(DomainError):
    """The map service did not answer usefully. Retryable: it usually will."""

    status_code = 503
    code = "geocoding_unavailable"
    retryable = True

    def __init__(self) -> None:
        super().__init__("The address lookup is not answering right now. Try again in a moment.")


@dataclass(frozen=True)
class Place:
    """What a point is called. Any part may be missing (open desert, the sea)."""

    city_en: str | None
    city_ar: str | None
    district_en: str | None
    district_ar: str | None


class ReverseGeocoder(Protocol):
    async def reverse(self, *, latitude: float, longitude: float) -> Place: ...


class NotConfiguredGeocoder:
    async def reverse(self, *, latitude: float, longitude: float) -> Place:
        raise IntegrationNotConfiguredError("Address lookup")


def _first(address: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = address.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def parse_address(address: dict[str, Any]) -> tuple[str | None, str | None]:
    """`(city, district)` from a Nominatim `address` object. Pure, for tests.

    A district that only repeats the city ("Riyadh, Riyadh") is dropped.
    """
    city = _first(address, _CITY_KEYS)
    district = _first(address, _DISTRICT_KEYS)
    if district and city and district.casefold() == city.casefold():
        district = None
    return city, district


class NominatimGeocoder:
    """Nominatim's `/reverse`, asked once per language."""

    def __init__(self, *, base_url: str, user_agent: str, timeout_seconds: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds

    async def _lookup(
        self, client: httpx.AsyncClient, *, latitude: float, longitude: float, language: str
    ) -> dict[str, Any]:
        response = await client.get(
            f"{self.base_url}/reverse",
            params={
                "lat": f"{latitude:.6f}",
                "lon": f"{longitude:.6f}",
                "format": "jsonv2",
                "addressdetails": 1,
                "zoom": 16,
                "accept-language": language,
            },
        )
        response.raise_for_status()
        body = response.json()
        address = body.get("address") if isinstance(body, dict) else None
        return address if isinstance(address, dict) else {}

    async def reverse(self, *, latitude: float, longitude: float) -> Place:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, headers={"User-Agent": self.user_agent}
            ) as client:
                english = await self._lookup(
                    client, latitude=latitude, longitude=longitude, language="en"
                )
                arabic = await self._lookup(
                    client, latitude=latitude, longitude=longitude, language="ar"
                )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("reverse_geocode_failed", extra={"error": str(exc)})
            raise GeocodingUnavailableError() from exc
        city_en, district_en = parse_address(english)
        city_ar, district_ar = parse_address(arabic)
        return Place(
            city_en=city_en, city_ar=city_ar, district_en=district_en, district_ar=district_ar
        )


def build_geocoder(settings: Any) -> ReverseGeocoder:
    if not settings.geocoder_url:
        return NotConfiguredGeocoder()
    return NominatimGeocoder(
        base_url=settings.geocoder_url,
        # Nominatim's policy: say who is asking, and how to reach them.
        user_agent=f"NOVA/1.0 (+{settings.public_app_url})",
        timeout_seconds=settings.geocoder_timeout_seconds,
    )
