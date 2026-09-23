"""discovery · APPLICATION layer — marketplace use cases.

Layer rule: domain, repository, models, events. No fastapi.
Services flush, never commit — the router owns the transaction boundary.

Two services, because the marketplace is asked two different questions from
two different sides of the authentication boundary:

  - `DiscoveryService` is public and has no tenant. It answers "what is out
    there", and records that a customer was sent somewhere.
  - `AttributionService` is tenant-scoped and is called from inside a booking
    request, where the tenant is already fixed. It answers the single question
    booking asks: does this token make the booking a marketplace booking?

Keeping them apart means the tenant-scoped half never carries the machinery for
resolving a tenant it already knows, and the public half never holds a
repository bound to a tenant it has not identified yet.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish_event
from app.modules.catalog.service import ListingCard, PublicCatalogService
from app.modules.discovery.domain import (
    WORLD_BBOX,
    SearchSort,
    bounding_box,
    distance_km,
    hash_referral_token,
    intersect_boxes,
    is_referral_live,
    new_referral_token,
    normalize_search_term,
    parse_bbox,
    referral_expiry,
    resolve_search_order,
    validate_availability_window,
    validate_coordinate_pair,
    validate_radius_km,
)
from app.modules.discovery.events import MarketplaceReferralRecorded
from app.modules.discovery.exceptions import ListingNotFoundError
from app.modules.discovery.models import MarketplaceReferral
from app.modules.discovery.repository import MarketplaceReferralRepository

#: How far past the requested page a geo search reads before trimming corners.
#: A bounding box is at most 4/pi — about 27% — larger than the circle it
#: contains, so a fixed cushion covers the rows that will be dropped while
#: keeping the query bounded.
_GEO_OVERFETCH = 50

#: Default search radius when coordinates are given without one. City-sized:
#: wide enough to cover Riyadh's inner districts, narrow enough that "near me"
#: still means something.
_DEFAULT_RADIUS_KM = 25.0


@dataclass(frozen=True)
class MapSearchResult:
    """The pins for one map view, and whether the cap cut any off."""

    cards: list[ListingCard]
    truncated: bool


@dataclass(frozen=True)
class OfferedSlot:
    """One bookable slot, with the provider who would perform it."""

    provider: Any
    slot: Any


@dataclass(frozen=True)
class PublicAvailability:
    """Slots for one service across every provider qualified for it."""

    business: Any
    service: Any
    slots: list[OfferedSlot]


@dataclass(frozen=True)
class IssuedReferral:
    """What `record_referral` hands back. The token is shown exactly once."""

    token: str
    expires_at: datetime
    business_id: UUID
    tenant_id: UUID


@dataclass(frozen=True)
class Storefront:
    """A business, its branches, and what each branch sells.

    Holds catalog's ORM rows rather than copies of them, the same way
    `BookingService` reads a `Service` straight from `CatalogService`. The
    router maps them to schemas; nothing here mutates them.
    """

    business: Any
    locations: list[Any]
    services: list[Any]
    providers: list[Any]
    photos: list[Any] = field(default_factory=list)


class DiscoveryService:
    """The public marketplace: search, storefront, and the referral record.

    Composed of two halves that meet only in `record_referral`:

      - `catalog` — read-only, cross-tenant, published rows only — answers what
        there is to find, and
      - a referral repository, this module's own table, which records that we
        found it for somebody.

    `referral_repository_for` is a factory rather than an injected repository
    because a referral's tenant is not known until a storefront has been
    resolved: the request arrives carrying a slug and nothing else.
    """

    def __init__(
        self,
        *,
        catalog: PublicCatalogService,
        session: AsyncSession,
        referral_repository_for: Callable[[UUID], Awaitable[MarketplaceReferralRepository]],
        max_availability_days: int = 14,
        max_public_slots: int = 500,
    ) -> None:
        self.catalog = catalog
        self.session = session
        self._referral_repository_for = referral_repository_for
        self.max_availability_days = max_availability_days
        self.max_public_slots = max_public_slots

    # --- search -------------------------------------------------------------

    async def search(
        self,
        *,
        term: str | None = None,
        city: str | None = None,
        category: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_km: float | None = None,
        bbox: str | None = None,
        sort: SearchSort = "default",
        limit: int = 20,
        offset: int = 0,
    ) -> list[ListingCard]:
        """Published branches matching the filters, nearest first when located.

        `sort="rating"` ranks by the confidence-weighted rating score instead
        (`catalog.domain.rating_score`), with or without a position.

        Geography is a two-step: the database narrows to a bounding box it can
        use an index for, and `distance_km` then trims the corners of that
        square down to the circle the customer actually asked for. Trigonometry
        in SQL would be exact but could not use an index; the box alone would
        report a branch 40km away as being within 30.

        `bbox` is a map viewport, `west,south,east,north`. A rectangle asked for
        is a rectangle answered, so on its own it needs no trimming and the
        database pages it like any other filter. Given together with a radius the
        two are intersected, and the circle is trimmed as above.
        """
        validate_coordinate_pair(latitude, longitude)
        order = resolve_search_order(sort, located=latitude is not None)

        box = None
        origin: tuple[float, float] | None = None
        radius = _DEFAULT_RADIUS_KM
        if latitude is not None and longitude is not None:
            radius = validate_radius_km(radius_km if radius_km is not None else _DEFAULT_RADIUS_KM)
            origin = (latitude, longitude)
            box = bounding_box(latitude=latitude, longitude=longitude, radius_km=radius)

        # `is not None`, not truthiness: `?bbox=` is a malformed viewport and
        # should be refused, not quietly read as "no viewport".
        if bbox is not None:
            viewport = parse_bbox(bbox)
            box = viewport if box is None else intersect_boxes(box, viewport)
            if box is None:
                return []  # the circle and the viewport never meet

        cards = await self.catalog.search(
            term=normalize_search_term(term),
            city=city.strip() if city else None,
            category=category.strip() if category else None,
            bounding_box=box,
            order="rating" if order == "rating" else "name",
            # The database pages the result except under a radius. There the
            # box over-selects, and the corner rows have to be dropped *before*
            # the page is cut or the page comes back short — so over-fetch a
            # bounded window and slice below.
            limit=limit if origin is None else limit + offset + _GEO_OVERFETCH,
            offset=offset if origin is None else 0,
        )

        if origin is None:
            return cards

        origin_lat, origin_lng = origin
        measured: list[ListingCard] = []
        for card in cards:
            if card.location.latitude is None or card.location.longitude is None:
                continue
            km = distance_km(
                from_lat=origin_lat,
                from_lng=origin_lng,
                to_lat=card.location.latitude,
                to_lng=card.location.longitude,
            )
            if km > radius:
                continue
            measured.append(
                ListingCard(
                    business=card.business,
                    location=card.location,
                    starting_price=card.starting_price,
                    currency=card.currency,
                    distance_km=round(km, 2),
                )
            )

        # Nearest first: once coordinates are given, distance is the ranking the
        # customer means and alphabetical order stops being useful — unless they
        # asked for the best-rated, in which case the database's rating order
        # survives the corner-trimming above (it is a stable filter) and
        # distance only breaks ties. The id tiebreak keeps the order total, so
        # paging cannot repeat a row.
        if order == "distance":
            measured.sort(key=lambda card: (card.distance_km or 0.0, str(card.location.id)))
        return measured[offset : offset + limit]

    async def search_on_map(
        self,
        *,
        term: str | None = None,
        city: str | None = None,
        category: str | None = None,
        bbox: str | None = None,
        limit: int = 200,
    ) -> MapSearchResult:
        """The branches a map can draw: the search filters, minus the paging.

        Not paged, because a page of pins is a map with holes in it. The cap
        bounds the response instead, and `truncated` says when it bit — one row
        past `limit` is read to find that out — so the client can ask the
        customer to zoom in rather than showing a partial map as a whole one.

        With no viewport the whole globe is searched (`WORLD_BBOX`), which is
        what keeps branches that have no coordinates off the map.
        """
        cards = await self.search(
            term=term,
            city=city,
            category=category,
            bbox=bbox if bbox is not None else WORLD_BBOX,
            limit=limit + 1,
        )
        return MapSearchResult(cards=cards[:limit], truncated=len(cards) > limit)

    # --- storefront ---------------------------------------------------------

    async def get_storefront(self, slug: str) -> Storefront:
        """Everything a customer needs in order to choose, in one call.

        One call rather than four because the alternative is a page filling in
        over four round trips, and because these lists are meaningless apart: a
        service belongs to a branch, and a provider is only bookable for the
        services they are qualified for.
        """
        business = await self.catalog.get_listed_business(slug)
        if business is None:
            raise ListingNotFoundError(slug)

        locations = await self.catalog.list_locations(business.id)
        location_ids = [location.id for location in locations]

        return Storefront(
            business=business,
            locations=locations,
            services=await self.catalog.list_services(location_ids),
            providers=await self.catalog.list_providers(location_ids),
            photos=await self.catalog.photos_for(business.id),
        )

    async def covers_for(self, business_ids: list[UUID]) -> dict[UUID, Any]:
        """Search cards' cover photos, one query for the whole page."""
        return await self.catalog.covers_for(business_ids)

    async def read_public_photo(self, photo_id: UUID, variant: str) -> bytes | None:
        return await self.catalog.read_public_photo(photo_id, variant)

    async def get_bookable_service(self, slug: str, service_id: UUID) -> tuple[Any, Any]:
        """Resolves a service *through* its storefront. Returns `(business, service)`.

        The slug is not decoration. A bare `service_id` on a public route would
        let anyone read any service on the platform by guessing a UUID,
        including one belonging to a de-listed salon. Requiring both means a
        service has to be reachable from a published storefront to be visible,
        and the mismatch case raises the same vague error as a missing one.
        """
        business = await self.catalog.get_listed_business(slug)
        if business is None:
            raise ListingNotFoundError(slug)

        service = await self.catalog.get_public_service(service_id)
        if service is None:
            raise ListingNotFoundError(slug)

        locations = await self.catalog.list_locations(business.id)
        if service.location_id not in {location.id for location in locations}:
            raise ListingNotFoundError(slug)

        return business, service

    async def list_bookable_providers(self, service_id: UUID, location_id: UUID) -> list[Any]:
        """The providers who may actually perform this service, with their names.

        Availability is asked one provider at a time, so the slot picker needs
        this list first — and it has to come from the qualification table rather
        than from "everyone at the branch", or the marketplace would offer a
        customer a stylist the salon never approved for the treatment.

        Intersected with the branch's provider list rather than trusting the
        qualification rows alone, so a provider who has since been retired or
        deactivated drops out: `_public_provider` is applied on that side.
        """
        qualified = set(await self.catalog.list_qualified_provider_ids(service_id))
        return [
            provider
            for provider in await self.catalog.list_providers([location_id])
            if provider.id in qualified
        ]

    async def public_availability(
        self,
        slug: str,
        service_id: UUID,
        *,
        date_from: datetime,
        date_to: datetime,
        availability_reader: Callable[[UUID], Awaitable[Any]],
    ) -> PublicAvailability:
        """Free slots for one service, across every provider qualified for it.

        Aggregated per service rather than per provider because a customer
        picks a treatment and a time, and only sometimes a particular stylist;
        making them choose a stylist before they can see any times inverts
        that.

        `availability_reader` is passed in rather than held, because reading
        availability means a `BookingService` and `booking` already imports this
        module for attribution — holding one here would close an import cycle.
        The router supplies the wiring; the rules stay here.

        Both bounds below exist because this route is anonymous. The window
        caps the date dimension and the slot cap catches the other one, a salon
        with a great many stylists. Truncation is chronological, after sorting,
        so it reads as "the next N available times" rather than dropping one
        stylist's day.
        """
        validate_availability_window(
            date_from=date_from, date_to=date_to, max_days=self.max_availability_days
        )

        business, service = await self.get_bookable_service(slug, service_id)
        providers = await self.list_bookable_providers(service_id, service.location_id)

        bookings = await availability_reader(business.tenant_id)

        offered: list[OfferedSlot] = []
        for provider in providers:
            for slot in await bookings.availability(
                provider_id=provider.id,
                service_id=service_id,
                date_from=date_from,
                date_to=date_to,
            ):
                offered.append(OfferedSlot(provider=provider, slot=slot))

        # Chronological across providers: the customer is choosing a time, and
        # a list grouped by stylist makes them scan it several times over.
        offered.sort(key=lambda o: (o.slot.starts_at, str(o.provider.id)))

        return PublicAvailability(
            business=business, service=service, slots=offered[: self.max_public_slots]
        )

    # --- referral -----------------------------------------------------------

    async def record_referral(self, slug: str, *, now: datetime | None = None) -> IssuedReferral:
        """Records that NOVA sent a customer to this storefront.

        This is the writer ADR-0008 was waiting for, and every part of it is
        shaped by the fact that the row eventually costs a salon 35%:

          - it is created server-side from a storefront the *server* resolved,
            so a client cannot assert a referral it was never given;
          - only the token's hash is stored, so the table is not a supply of
            working ones; and
          - it expires in 30 days (docs/11 section 3 rule 4).

        Note what it deliberately does not record: who clicked. Whether this
        customer is new to this business is billing's question, settled by a
        unique index at completion time, and answering it here too would be a
        second place for "charged as new exactly once, forever" to go wrong.
        """
        now = now or datetime.now(UTC)

        business = await self.catalog.get_listed_business(slug)
        if business is None:
            raise ListingNotFoundError(slug)

        token = new_referral_token()
        # The click arrived with no tenant; the storefront lookup just supplied
        # one, so the write happens under ordinary tenant isolation.
        repository = await self._referral_repository_for(business.tenant_id)
        referral = MarketplaceReferral(
            tenant_id=business.tenant_id,
            business_id=business.id,
            token_hash=hash_referral_token(token),
            expires_at=referral_expiry(clicked_at=now),
        )
        repository.add(referral)
        await self.session.flush()

        await publish_event(
            self.session,
            MarketplaceReferralRecorded(
                tenant_id=business.tenant_id,
                business_id=business.id,
                referral_id=referral.id,
            ),
        )

        return IssuedReferral(
            token=token,
            expires_at=referral.expires_at,
            business_id=business.id,
            tenant_id=business.tenant_id,
        )


class AttributionService:
    """Answers, for one tenant, whether a referral token attributes a booking.

    Tenant-scoped and deliberately tiny: it is called from inside
    `POST /bookings`, where the tenant is already fixed by the path, and it
    exists so that booking never has to know what a referral is made of.
    """

    def __init__(self, *, referrals: MarketplaceReferralRepository) -> None:
        self.referrals = referrals

    async def attributes_to_marketplace(
        self,
        token: str | None,
        *,
        business_id: UUID,
        booking_id: UUID | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Whether this token proves NOVA introduced the customer to *this* business.

        Every way of answering wrong answers `False`, because ADR-0008 fixed
        the direction ambiguity resolves in: under-charging NOVA is lost
        revenue, while charging a salon for a customer it already had is the P1
        docs/11 section 3 names. A token that is absent, unknown, expired, or
        issued for a different business is therefore simply not a marketplace
        booking.

        The `business_id` check is what stops one salon's referral being spent
        at another — the cheapest attribution fraud available to a client, and
        the only one it can attempt by hand. The repository being tenant-scoped
        already blocks the cross-tenant case; this blocks the two-businesses-
        in-one-tenant case as well.
        """
        if not token:
            return False

        now = now or datetime.now(UTC)
        referral = await self.referrals.get_by_token_hash(hash_referral_token(token))

        if referral is None:
            return False
        if referral.business_id != business_id:
            return False
        if not is_referral_live(expires_at=referral.expires_at, now=now):
            return False

        # Stamped rather than consumed: the row is the audit trail behind a
        # commission line, and a disputed invoice is settled by showing which
        # booking claimed which click. It is not marked single-use — a customer
        # who books two services off one visit came through the marketplace
        # both times, and docs/11 section 3 rule 2 already makes only the first
        # of them billable.
        referral.consumed_at = now
        referral.consumed_by_booking_id = booking_id
        return True
