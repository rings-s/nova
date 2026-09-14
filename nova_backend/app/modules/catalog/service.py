"""Application layer for the catalog module.

Services flush, never commit — the router owns the transaction boundary.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.core.events import publish_event
from app.modules.catalog.domain import (
    generate_slug,
    require_bilingual_text,
    validate_coordinates,
    validate_gcc_phone,
    validate_service_duration,
    validate_service_price,
    validate_timezone,
)
from app.modules.catalog.events import BusinessCreated, LocationCreated, ServicePublished
from app.modules.catalog.exceptions import (
    BusinessNotFoundError,
    CrossLocationAssignmentError,
    DuplicateSlugError,
    LocationNotFoundError,
    ProviderNotFoundError,
    ServiceNotFoundError,
)
from app.modules.catalog.models import Business, Location, Provider, ProviderService, Service
from app.modules.catalog.repository import (
    BusinessRepository,
    LocationRepository,
    ProviderRepository,
    PublicCatalogRepository,
    ServiceRepository,
)


class CatalogService:
    def __init__(
        self,
        *,
        businesses: BusinessRepository,
        locations: LocationRepository,
        services: ServiceRepository,
        providers: ProviderRepository,
        tenant_id: UUID,
        allowed_phone_country_codes: list[str],
    ) -> None:
        self.businesses = businesses
        self.locations = locations
        self.services = services
        self.providers = providers
        self.tenant_id = tenant_id
        self.allowed_phone_country_codes = allowed_phone_country_codes

    @property
    def session(self):
        """The one session every catalog repository shares.

        `get_catalog_service` constructs all four repositories from the same
        request-scoped session, so any of them names the same transaction —
        which is what lets outbox writes commit atomically with the row they
        describe.
        """
        return self.businesses.session

    # --- Business -----------------------------------------------------------

    async def create_business(
        self,
        *,
        name_en: str,
        name_ar: str,
        description_en: str | None = None,
        description_ar: str | None = None,
    ) -> Business:
        require_bilingual_text(name_en, name_ar)
        slug = generate_slug(name_en)
        if await self.businesses.get_by_slug(slug) is not None:
            raise DuplicateSlugError(slug)

        business = Business(
            tenant_id=self.tenant_id,
            name_en=name_en,
            name_ar=name_ar,
            slug=slug,
            description_en=description_en,
            description_ar=description_ar,
        )
        self.businesses.add(business)
        await self.businesses.session.flush()

        await publish_event(
            self.session, BusinessCreated(tenant_id=self.tenant_id, business_id=business.id)
        )
        return business

    async def get_business(self, business_id: UUID) -> Business:
        business = await self.businesses.get(business_id)
        if business is None:
            raise BusinessNotFoundError(business_id)
        return business

    # --- Location -----------------------------------------------------------

    async def create_location(
        self,
        *,
        business_id: UUID,
        name_en: str,
        name_ar: str,
        phone: str,
        timezone: str = "Asia/Riyadh",
        city: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> Location:
        # Verifies the business exists *and* belongs to this tenant, because the
        # repository is tenant-scoped.
        await self.get_business(business_id)

        require_bilingual_text(name_en, name_ar)
        validate_gcc_phone(phone, self.allowed_phone_country_codes)
        validate_timezone(timezone)
        validate_coordinates(latitude, longitude)

        slug = generate_slug(name_en)
        location = Location(
            tenant_id=self.tenant_id,
            business_id=business_id,
            name_en=name_en,
            name_ar=name_ar,
            slug=slug,
            phone=phone,
            timezone=timezone,
            city=city,
            latitude=latitude,
            longitude=longitude,
        )
        self.locations.add(location)
        await self.locations.session.flush()

        await publish_event(
            self.session,
            LocationCreated(
                tenant_id=self.tenant_id, business_id=business_id, location_id=location.id
            ),
        )
        return location

    async def get_location(self, location_id: UUID) -> Location:
        location = await self.locations.get(location_id)
        if location is None:
            raise LocationNotFoundError(location_id)
        return location

    async def list_locations(self, business_id: UUID) -> list[Location]:
        await self.get_business(business_id)
        return await self.locations.list_for_business(business_id)

    # --- Service ------------------------------------------------------------

    async def create_service(
        self,
        *,
        location_id: UUID,
        name_en: str,
        name_ar: str,
        duration_minutes: int,
        price: Decimal,
        currency: str = "SAR",
        category: str | None = None,
        description_en: str | None = None,
        description_ar: str | None = None,
    ) -> Service:
        await self.get_location(location_id)

        require_bilingual_text(name_en, name_ar)
        validate_service_duration(duration_minutes)
        validate_service_price(price)

        service = Service(
            tenant_id=self.tenant_id,
            location_id=location_id,
            name_en=name_en,
            name_ar=name_ar,
            description_en=description_en,
            description_ar=description_ar,
            category=category,
            duration_minutes=duration_minutes,
            price=price,
            currency=currency,
        )
        self.services.add(service)
        await self.services.session.flush()

        await publish_event(
            self.session,
            ServicePublished(
                tenant_id=self.tenant_id, location_id=location_id, service_id=service.id
            ),
        )
        return service

    async def get_service(self, service_id: UUID) -> Service:
        service = await self.services.get(service_id)
        if service is None:
            raise ServiceNotFoundError(service_id)
        return service

    async def list_services(self, location_id: UUID) -> list[Service]:
        await self.get_location(location_id)
        return await self.services.list_for_location(location_id)

    # --- Provider -----------------------------------------------------------

    async def create_provider(
        self,
        *,
        location_id: UUID,
        name_en: str,
        name_ar: str,
        title_en: str | None = None,
        title_ar: str | None = None,
    ) -> Provider:
        await self.get_location(location_id)
        require_bilingual_text(name_en, name_ar)

        provider = Provider(
            tenant_id=self.tenant_id,
            location_id=location_id,
            name_en=name_en,
            name_ar=name_ar,
            title_en=title_en,
            title_ar=title_ar,
        )
        self.providers.add(provider)
        await self.providers.session.flush()
        return provider

    async def get_provider(self, provider_id: UUID) -> Provider:
        provider = await self.providers.get(provider_id)
        if provider is None:
            raise ProviderNotFoundError(provider_id)
        return provider

    async def list_providers(self, location_id: UUID) -> list[Provider]:
        await self.get_location(location_id)
        return await self.providers.list_for_location(location_id)

    async def assign_service_to_provider(
        self, provider_id: UUID, service_id: UUID
    ) -> ProviderService:
        provider = await self.get_provider(provider_id)
        service = await self.get_service(service_id)

        # A provider works at one location; a service is offered at one
        # location. Assigning across them would let booking schedule a provider
        # who is physically somewhere else.
        if provider.location_id != service.location_id:
            raise CrossLocationAssignmentError()

        assignment = self.providers.assign_service(provider_id, service_id)
        await self.providers.session.flush()
        return assignment

    async def is_provider_qualified(self, provider_id: UUID, service_id: UUID) -> bool:
        return await self.providers.is_qualified(provider_id, service_id)

    # --- marketplace listing ------------------------------------------------

    async def set_listing_visibility(self, business_id: UUID, *, is_listed: bool) -> Business:
        """Shows or hides this business on the public marketplace (ADR-0010).

        Separate from any notion of "active" on purpose. docs/11 section 8 ends
        the dunning ladder with "marketplace listing hidden. The calendar,
        queue, and existing bookings keep working" — so the switch that billing
        eventually pulls has to remove the salon from search *without* touching
        anything it is already running.
        """
        business = await self.get_business(business_id)
        business.is_listed = is_listed
        await self.businesses.session.flush()
        return business


# --- the public marketplace read path ------------------------------------


@dataclass(frozen=True)
class ListingCard:
    """One search result: a branch, and the cheapest thing it sells.

    A branch rather than a business, because a customer books at an address.
    A chain's Riyadh and Jeddah branches are different answers to "near me",
    and collapsing them into one card would force the customer to open a
    storefront to find out whether the salon is anywhere near them.

    `distance_km` is None unless the search supplied coordinates.
    """

    business: Business
    location: Location
    starting_price: Decimal | None
    currency: str | None
    distance_km: float | None = None


class PublicCatalogService:
    """Reads published listings across every tenant, for the marketplace.

    The counterpart to `CatalogService`, and its opposite in exactly one
    respect: it has no `tenant_id`. Everything else about it is narrower — it
    is read-only, and it can only see rows a business has published.

    It lives in `catalog` because these are catalog's tables and the dependency
    rule keeps queries in the module that owns the schema. It is consumed by
    `discovery`, which owns the HTTP surface and the referral record but must
    not reach into these tables itself.

    Callers are responsible for opening the RLS window first — see
    `discovery.dependencies.get_discovery_service`, which is the only place
    that happens. Without it every method here correctly returns nothing.
    """

    def __init__(self, *, listings: PublicCatalogRepository) -> None:
        self.listings = listings

    async def search(
        self,
        *,
        term: str | None = None,
        city: str | None = None,
        category: str | None = None,
        bounding_box: tuple[float, float, float, float] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ListingCard]:
        rows = await self.listings.search(
            term=term,
            city=city,
            category=category,
            bounding_box=bounding_box,
            limit=limit,
            offset=offset,
        )
        return [
            ListingCard(
                business=business,
                location=location,
                starting_price=starting_price,
                currency=currency,
            )
            for business, location, starting_price, currency in rows
        ]

    async def get_listed_business(self, slug: str) -> Business | None:
        """The storefront, or None. Discovery decides what None means.

        Returning None rather than raising keeps catalog free of discovery's
        vocabulary: "this slug is not published" is a marketplace concept, and
        `ListingNotFoundError` is deliberately vague about why for reasons that
        belong to that module.
        """
        return await self.listings.get_business_by_slug(slug)

    async def list_locations(self, business_id: UUID) -> list[Location]:
        return await self.listings.list_locations(business_id)

    async def list_services(self, location_ids: list[UUID]) -> list[Service]:
        return await self.listings.list_services(location_ids)

    async def list_providers(self, location_ids: list[UUID]) -> list[Provider]:
        return await self.listings.list_providers(location_ids)

    async def list_qualified_provider_ids(self, service_id: UUID) -> list[UUID]:
        return await self.listings.list_qualified_provider_ids(service_id)

    async def get_public_service(self, service_id: UUID) -> Service | None:
        return await self.listings.get_public_service(service_id)
