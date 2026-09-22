"""discovery · DELIVERY layer — HTTP.

Layer rule: may import schemas, service, dependencies.
Must not import models or repositories, and must contain no business rules.

Every route here is unauthenticated, which makes this file the platform's
attack surface in a way no other router is. ADR-0006 established that NOVA
fails closed and that every endpoint requires a bearer token; ADR-0010 carves
out this one exception, because a marketplace a customer must log in to browse
is not a marketplace. The exception is paid for in four ways:

  - Read-only. The single write is `POST /referrals`, which creates a row about
    NOVA's own behaviour and touches nothing a business owns.
  - Published rows only, enforced twice — in the query predicates and again in
    Postgres RLS (`app.discovery_mode`), which is SELECT-only.
  - Every route is IP rate-limited, since there is no principal to limit by.
  - The projection is curated in `schemas.py`: no phone numbers in search
    results, no internal flags, no counts that would let the listing be used to
    size a competitor's business.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.pagination import PageParams
from app.core.schemas import Page
from app.core.throttling import (
    discovery_availability_rate_limit,
    discovery_read_rate_limit,
    discovery_referral_rate_limit,
)
from app.db.session import set_tenant_scope
from app.modules.booking.dependencies import build_booking_service
from app.modules.booking.service import BookingService
from app.modules.catalog.domain import rating_average
from app.modules.catalog.service import ListingCard
from app.modules.discovery.dependencies import get_discovery_service
from app.modules.discovery.domain import SearchSort
from app.modules.discovery.schemas import (
    ListingCardOut,
    ListingFeature,
    ListingFeatureCollection,
    ListingGeometry,
    PublicAvailabilityOut,
    PublicSlotOut,
    ReferralOut,
    StorefrontLocationOut,
    StorefrontOut,
    StorefrontProviderOut,
    StorefrontServiceOut,
)
from app.modules.discovery.service import DiscoveryService


async def _availability_reader(session: AsyncSession, tenant_id: UUID) -> BookingService:
    """A booking service for a tenant the marketplace has just resolved.

    Composed here, in the delivery layer, rather than in `dependencies.py`,
    and the reason is structural: `discovery.dependencies` is imported by
    `booking.dependencies` to build the attribution half, so importing booking
    back from it would close a cycle. Routers may compose other modules' wiring;
    the service and dependency layers below them stay acyclic.

    The `set_tenant_scope` call widens this transaction's RLS window from
    "published listings" to "one tenant", which is a real widening and is why
    it is named rather than inlined. It is safe for as long as the only caller
    keeps doing what it does today — read free slots and return — and `SET
    LOCAL` closes the window when the request's transaction ends.
    """
    await set_tenant_scope(session, tenant_id)
    return build_booking_service(session, tenant_id)


# Not nested under a tenant — the one router in NOVA that is not, because the
# customer has not chosen a tenant yet and choosing one is what this does.
router = APIRouter(prefix="/discovery", tags=["discovery"])


def _listing_card(card: ListingCard) -> ListingCardOut:
    """The public projection of a search hit, shared by the list and the map.

    One function so the two cannot drift: whatever the search result leaves out
    (ADR-0010: phone numbers, internal flags, counts) the map leaves out too.
    """
    return ListingCardOut(
        business_id=card.business.id,
        tenant_id=card.business.tenant_id,
        slug=card.business.slug,
        name_en=card.business.name_en,
        name_ar=card.business.name_ar,
        description_en=card.business.description_en,
        description_ar=card.business.description_ar,
        location_id=card.location.id,
        location_name_en=card.location.name_en,
        location_name_ar=card.location.name_ar,
        city=card.location.city,
        latitude=card.location.latitude,
        longitude=card.location.longitude,
        timezone=card.location.timezone,
        starting_price=card.starting_price,
        currency=card.currency,
        distance_km=card.distance_km,
        rating_count=card.business.rating_count,
        rating_average=rating_average(card.business.rating_sum, card.business.rating_count),
    )


@router.get(
    "/businesses",
    response_model=Page[ListingCardOut],
    dependencies=[Depends(discovery_read_rate_limit)],
)
async def search_businesses(
    q: str | None = Query(default=None, max_length=120, description="Free text, EN or AR."),
    city: str | None = Query(default=None, max_length=120),
    category: str | None = Query(default=None, max_length=120),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float | None = Query(default=None, gt=0, le=100),
    bbox: str | None = Query(
        default=None,
        max_length=120,
        description="A map viewport, `west,south,east,north` in degrees.",
    ),
    sort: SearchSort = Query(
        default="default",
        description="`default` (nearest first when located, else by name), "
        "`distance` (needs coordinates), or `rating` (best rated first).",
    ),
    params: PageParams = Depends(),
    service: DiscoveryService = Depends(get_discovery_service),
) -> Page[ListingCardOut]:
    """Finds bookable branches. The marketplace's front door.

    `latitude`/`longitude` must be supplied together; `radius_km` defaults to a
    city-sized 25km. With coordinates the result is ordered nearest-first,
    otherwise alphabetically. `bbox` keeps only branches inside a map viewport,
    and combines with the radius by intersection.
    """
    cards = await service.search(
        term=q,
        city=city,
        category=category,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        bbox=bbox,
        sort=sort,
        limit=params.limit,
        offset=params.offset,
    )
    return Page(
        items=[_listing_card(card) for card in cards],
        # No `total`: this result is paged, and reporting the size of the page
        # as the size of the result set is worse than reporting nothing. A real
        # count means a second aggregate over the same predicates, which is a
        # cost to pay when a client actually needs to render "1 of 12 pages".
    )


# `/map`, not `/businesses/map`: the latter would be captured by
# `/businesses/{slug}` above it, and would shadow any business whose slug is
# "map" besides.
@router.get(
    "/map",
    response_model=ListingFeatureCollection,
    dependencies=[Depends(discovery_read_rate_limit)],
)
async def map_businesses(
    q: str | None = Query(default=None, max_length=120, description="Free text, EN or AR."),
    city: str | None = Query(default=None, max_length=120),
    category: str | None = Query(default=None, max_length=120),
    bbox: str | None = Query(
        default=None,
        max_length=120,
        description="A map viewport, `west,south,east,north` in degrees.",
    ),
    limit: int = Query(default=200, ge=1, le=500),
    service: DiscoveryService = Depends(get_discovery_service),
) -> ListingFeatureCollection:
    """The same search as `/businesses`, as GeoJSON for a Leaflet map.

    Only branches with coordinates are returned, and they are not paged: a map
    shows what is in view or it misleads. `limit` caps the response instead, and
    `truncated` is true when the cap cut branches off, so a client can ask the
    customer to zoom in. A `bbox` from `map.getBounds().toBBoxString()` goes
    through as it is.

    The body is a GeoJSON FeatureCollection (RFC 7946) served as
    `application/json`, not the `application/geo+json` the RFC registers.
    FastAPI documents a route's error responses under the route's own media
    type, so a `geo+json` route would publish its errors as `geo+json` too,
    while `error_handlers` always sends them as JSON — and the contract test in
    `test_error_contract.py` exists to keep those two the same.
    """
    found = await service.search_on_map(
        term=q, city=city, category=category, bbox=bbox, limit=limit
    )
    return ListingFeatureCollection(
        features=[
            ListingFeature(
                id=card.location.id,
                # GeoJSON is [longitude, latitude]. Not a typo.
                geometry=ListingGeometry(
                    coordinates=(card.location.longitude, card.location.latitude)
                ),
                properties=_listing_card(card),
            )
            for card in found.cards
            # The search already leaves out branches with no coordinates; this
            # says so to the type checker, and to a reader, at the point of use.
            if card.location.latitude is not None and card.location.longitude is not None
        ],
        truncated=found.truncated,
    )


@router.get(
    "/businesses/{slug}",
    response_model=StorefrontOut,
    dependencies=[Depends(discovery_read_rate_limit)],
)
async def get_storefront(
    slug: str,
    service: DiscoveryService = Depends(get_discovery_service),
) -> StorefrontOut:
    """One business's public page: branches, services, and providers.

    Keyed by `slug` rather than id because the slug is the public, shareable
    identifier (docs/08 §147) and a customer arriving from a link has nothing
    else. A slug that is not published is a 404 — see `ListingNotFoundError`
    for why it is not a 403.
    """
    storefront = await service.get_storefront(slug)
    business = storefront.business
    return StorefrontOut(
        business_id=business.id,
        tenant_id=business.tenant_id,
        slug=business.slug,
        name_en=business.name_en,
        name_ar=business.name_ar,
        description_en=business.description_en,
        description_ar=business.description_ar,
        rating_count=business.rating_count,
        rating_average=rating_average(business.rating_sum, business.rating_count),
        locations=[StorefrontLocationOut.model_validate(row) for row in storefront.locations],
        services=[StorefrontServiceOut.model_validate(row) for row in storefront.services],
        providers=[StorefrontProviderOut.model_validate(row) for row in storefront.providers],
    )


@router.get(
    "/businesses/{slug}/services/{service_id}/availability",
    response_model=PublicAvailabilityOut,
    dependencies=[Depends(discovery_availability_rate_limit)],
)
async def get_public_availability(
    slug: str,
    service_id: UUID,
    date_from: datetime = Query(...),
    date_to: datetime = Query(...),
    session: AsyncSession = Depends(get_db_session),
    discovery: DiscoveryService = Depends(get_discovery_service),
) -> PublicAvailabilityOut:
    """Free slots for one service, across every provider qualified for it.

    Aggregated per service rather than per provider because a customer picks a
    treatment and a time, and only sometimes a particular stylist — asking them
    to choose a provider before they can see any times inverts that.

    The slots carry the same signed `slot_id` the authenticated availability
    route issues, so a slot found here can be booked directly and the server
    can still prove it offered exactly that slot (docs/07 §5).

    Rate-limited harder than the other two routes: free slots are the inverse
    of a provider's calendar, so this is an occupancy oracle for anyone willing
    to poll it. The limit bounds that rather than closing it — the same trade
    the authenticated route already makes, taken with no principal to blame.
    """
    availability = await discovery.public_availability(
        slug,
        service_id,
        date_from=date_from,
        date_to=date_to,
        availability_reader=lambda tenant_id: _availability_reader(session, tenant_id),
    )
    service = availability.service

    return PublicAvailabilityOut(
        business_id=availability.business.id,
        tenant_id=availability.business.tenant_id,
        service_id=service.id,
        location_id=service.location_id,
        duration_minutes=service.duration_minutes,
        price=service.price,
        currency=service.currency,
        slots=[
            PublicSlotOut(
                slot_id=offered.slot.slot_id,
                provider_id=offered.provider.id,
                provider_name_en=offered.provider.name_en,
                provider_name_ar=offered.provider.name_ar,
                location_id=offered.slot.location_id,
                service_id=offered.slot.service_id,
                starts_at=offered.slot.starts_at,
                ends_at=offered.slot.ends_at,
            )
            for offered in availability.slots
        ],
    )


@router.post(
    "/businesses/{slug}/referrals",
    response_model=ReferralOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(discovery_referral_rate_limit)],
)
async def record_referral(
    slug: str,
    session: AsyncSession = Depends(get_db_session),
    service: DiscoveryService = Depends(get_discovery_service),
) -> ReferralOut:
    """Records that NOVA sent this customer to this storefront.

    Called by the marketplace client when a customer opens a listing. The token
    it returns is what later makes their booking `marketplace` rather than
    `direct_link` — the writer ADR-0008 deferred until this surface existed.

    A POST, not a GET, because it writes; and the only write on this router.
    Note that it is genuinely NOVA's own record — nothing a business owns is
    created or changed, so an abusive caller can inflate NOVA's click counts
    and nothing else. Whether a click ever becomes money is decided later, by a
    completed booking and billing's own first-booking index.
    """
    issued = await service.record_referral(slug)
    await session.commit()
    return ReferralOut(
        referral_token=issued.token,
        business_id=issued.business_id,
        tenant_id=issued.tenant_id,
        expires_at=issued.expires_at,
    )
