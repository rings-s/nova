"""discovery · CONTRACT layer — API boundary DTOs.

Layer rule: pydantic only. These are not the domain model and not the table.

These schemas are the platform's only unauthenticated read surface, so what is
*absent* from them is as deliberate as what is present. `tenant_id` appears
because a customer must send it back to book. Branch phone numbers appear on a
storefront, which is the salon's own shop window, but never in search results —
otherwise one query returns a scrape-ready directory of every salon on NOVA,
which is the defect ADR-0007 found on the old unauthenticated `GET /tenants`.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.core.schemas import ApiSchema


class PublicPhotoOut(ApiSchema):
    """A photo of a listed business. `urls` maps each size to its image."""

    id: UUID
    kind: Literal["cover", "gallery"]
    width: int
    height: int
    urls: dict[str, str]


class ListingCardOut(ApiSchema):
    """One search result: a bookable branch, priced from."""

    business_id: UUID
    tenant_id: UUID
    slug: str
    name_en: str
    name_ar: str
    description_en: str | None = None
    description_ar: str | None = None

    location_id: UUID
    location_name_en: str
    location_name_ar: str
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str

    #: Cheapest bookable service at this branch — the "from 150 SAR" on a card.
    #: None when the branch has published no services yet.
    starting_price: Decimal | None = None
    currency: str | None = None
    #: Present only when the search supplied coordinates.
    distance_km: float | None = None
    #: Verified ratings (`review` module): how many, and their plain average.
    #: The search's `sort=rating` ranks by a confidence-weighted score instead,
    #: so one 5-star visit does not outrank hundreds averaging 4.8.
    rating_count: int = 0
    rating_average: float | None = None
    #: The business's cover photo, sized for a card. None without one.
    cover_url: str | None = None


class ListingGeometry(ApiSchema):
    type: Literal["Point"] = "Point"
    #: `[longitude, latitude]`: GeoJSON's order (RFC 7946 §3.1.1), the reverse
    #: of the `latitude`/`longitude` pair everywhere else in this API.
    coordinates: tuple[float, float]


class ListingFeature(ApiSchema):
    """A bookable branch as a GeoJSON Feature, ready for `L.geoJSON`.

    `properties` is `ListingCardOut` itself, so a map pin carries exactly what a
    search result does and nothing more: still no phone number, still no counts.
    """

    type: Literal["Feature"] = "Feature"
    #: The branch (location) id, so a client can key its markers on it.
    id: UUID
    geometry: ListingGeometry
    properties: ListingCardOut


class ListingFeatureCollection(ApiSchema):
    """Every branch in view, as GeoJSON (RFC 7946 §3.3)."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[ListingFeature]
    #: More branches matched than `limit` allowed, so the map is showing some of
    #: them. A foreign member, which RFC 7946 §6.1 permits, so a consumer that
    #: only knows GeoJSON is not disturbed by it.
    truncated: bool = False


class StorefrontLocationOut(ApiSchema):
    id: UUID
    name_en: str
    name_ar: str
    city: str | None = None
    #: The salon's own shop-window contact. Public here, never in search.
    phone: str
    timezone: str
    latitude: float | None = None
    longitude: float | None = None


class StorefrontServiceOut(ApiSchema):
    id: UUID
    location_id: UUID
    name_en: str
    name_ar: str
    description_en: str | None = None
    description_ar: str | None = None
    category: str | None = None
    duration_minutes: int
    price: Decimal
    currency: str


class StorefrontProviderOut(ApiSchema):
    id: UUID
    location_id: UUID
    name_en: str
    name_ar: str
    title_en: str | None = None
    title_ar: str | None = None


class StorefrontOut(ApiSchema):
    """A whole storefront: everything needed to pick a branch and a service."""

    business_id: UUID
    #: Needed to book: every booking route is nested under its tenant.
    tenant_id: UUID
    slug: str
    name_en: str
    name_ar: str
    description_en: str | None = None
    description_ar: str | None = None
    #: Verified ratings (`review` module): how many, and their plain average.
    #: The search's `sort=rating` ranks by a confidence-weighted score instead,
    #: so one 5-star visit does not outrank hundreds averaging 4.8.
    rating_count: int = 0
    rating_average: float | None = None
    #: Cover first, then the gallery in the business's order.
    photos: list[PublicPhotoOut] = []

    locations: list[StorefrontLocationOut]
    services: list[StorefrontServiceOut]
    providers: list[StorefrontProviderOut]


class ReferralOut(ApiSchema):
    """A recorded marketplace click.

    `referral_token` is returned exactly once and never again — only its hash
    is stored. The client passes it back on `POST /bookings`, which is what
    lets that booking be recorded as `marketplace` (ADR-0008).
    """

    referral_token: str
    business_id: UUID
    tenant_id: UUID
    expires_at: datetime


class PublicSlotOut(ApiSchema):
    """A bookable slot, as offered to a customer who has not signed in.

    Identical in shape to `booking.AvailableSlotOut`, and `slot_id` is the same
    signed value — so a slot discovered anonymously can be booked directly,
    with the server still able to verify it offered that exact slot.
    """

    slot_id: str
    provider_id: UUID
    provider_name_en: str
    provider_name_ar: str
    location_id: UUID
    service_id: UUID
    starts_at: datetime
    ends_at: datetime


class PublicAvailabilityOut(ApiSchema):
    """Slots for one service, across every provider qualified to perform it."""

    business_id: UUID
    tenant_id: UUID
    service_id: UUID
    location_id: UUID
    duration_minutes: int
    price: Decimal
    currency: str
    slots: list[PublicSlotOut] = Field(default_factory=list)
