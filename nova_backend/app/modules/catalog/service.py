"""Application layer for the catalog module.

Services flush, never commit — the router owns the transaction boundary.
"""

import asyncio
import uuid as uuid_module
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from uuid import UUID

from app.core.events import publish_event
from app.integrations.images import process_upload
from app.integrations.storage import ImageStore
from app.modules.catalog.domain import (
    MAX_GALLERY_PHOTOS,
    PHOTO_VARIANTS,
    generate_slug,
    photo_storage_key,
    require_bilingual_text,
    validate_coordinates,
    validate_gcc_phone,
    validate_photo_kind,
    validate_service_duration,
    validate_service_price,
    validate_timezone,
)
from app.modules.catalog.events import BusinessCreated, LocationCreated, ServicePublished
from app.modules.catalog.exceptions import (
    BusinessNotFoundError,
    CrossLocationAssignmentError,
    DuplicateSlugError,
    GalleryFullError,
    LocationNotFoundError,
    PhotoNotFoundError,
    ProviderNotFoundError,
    ServiceNotFoundError,
)
from app.modules.catalog.models import (
    Business,
    BusinessPhoto,
    Location,
    Provider,
    ProviderService,
    Service,
)
from app.modules.catalog.repository import (
    BusinessPhotoRepository,
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
        photos: BusinessPhotoRepository | None = None,
        images: ImageStore | None = None,
    ) -> None:
        self.photos = photos
        self.images = images
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

    async def list_businesses(self, *, limit: int = 20, offset: int = 0) -> list[Business]:
        return await self.businesses.list_ordered(limit=limit, offset=offset)

    async def get_business(self, business_id: UUID) -> Business:
        business = await self.businesses.get(business_id)
        if business is None:
            raise BusinessNotFoundError(business_id)
        return business

    # --- Photos ---------------------------------------------------------------

    def _photo_parts(self) -> tuple[BusinessPhotoRepository, ImageStore]:
        if self.photos is None or self.images is None:
            raise RuntimeError("CatalogService was built without photo storage.")
        return self.photos, self.images

    async def list_photos(self, business_id: UUID) -> list[BusinessPhoto]:
        photos, _ = self._photo_parts()
        await self.get_business(business_id)
        return await photos.list_for_business(business_id)

    async def add_photo(self, business_id: UUID, *, kind: str, data: bytes) -> BusinessPhoto:
        """Stores a new cover (replacing any old one) or gallery photo.

        The upload is decoded and re-encoded before anything is written
        (`integrations.images`), off the event loop because it is CPU work.
        Files go down before the row, so a row never points at nothing; a
        failure after that leaves at worst an unreferenced file.
        """
        photos, images = self._photo_parts()
        kind = validate_photo_kind(kind)
        await self.get_business(business_id)

        position = 0
        replaced: BusinessPhoto | None = None
        if kind == "gallery":
            count, top = await photos.gallery_stats(business_id)
            if count >= MAX_GALLERY_PHOTOS:
                raise GalleryFullError(MAX_GALLERY_PHOTOS)
            position = top + 1
        else:
            replaced = await photos.get_cover(business_id)

        processed = await asyncio.to_thread(process_upload, data)
        photo_id = uuid_module.uuid4()
        prefix = f"{self.tenant_id}/{photo_id}"
        for variant, image in processed.variants.items():
            await asyncio.to_thread(images.save, photo_storage_key(prefix, variant), image.data)

        if replaced is not None:
            await self._remove_photo(replaced)

        photo = photos.add(
            BusinessPhoto(
                id=photo_id,
                tenant_id=self.tenant_id,
                business_id=business_id,
                kind=kind,
                position=position,
                storage_prefix=prefix,
                width=processed.width,
                height=processed.height,
            )
        )
        await self.session.flush()
        return photo

    async def delete_photo(self, photo_id: UUID) -> None:
        photos, _ = self._photo_parts()
        photo = await photos.get(photo_id)
        if photo is None:
            raise PhotoNotFoundError(photo_id)
        await self._remove_photo(photo)

    async def read_photo(self, photo_id: UUID, variant: str) -> bytes:
        """The stored bytes of a photo in this tenant (dashboard previews)."""
        photos, images = self._photo_parts()
        photo = await photos.get(photo_id)
        if photo is None:
            raise PhotoNotFoundError(photo_id)
        data = await asyncio.to_thread(
            images.read, photo_storage_key(photo.storage_prefix, variant)
        )
        if data is None:
            raise PhotoNotFoundError(photo_id)
        return data

    async def _remove_photo(self, photo: BusinessPhoto) -> None:
        photos, images = self._photo_parts()
        prefix = photo.storage_prefix
        await photos.delete(photo)
        await self.session.flush()
        for variant in PHOTO_VARIANTS:
            await asyncio.to_thread(images.delete, photo_storage_key(prefix, variant))

    async def record_rating(self, business_id: UUID, rating: int) -> None:
        """Counts one verified rating toward this business's listing score.

        Called by `review.ReviewService` in the transaction that stores the
        review, so the totals can never disagree with the reviews table. The
        rating's 1..5 range is enforced by the caller's domain rule and again
        by `ck_businesses_rating_sum_in_range`.
        """
        if not await self.businesses.add_rating(business_id, rating):
            raise BusinessNotFoundError(business_id)

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

    async def set_location_position(
        self, location_id: UUID, *, latitude: float | None, longitude: float | None
    ) -> Location:
        """Puts a branch on the marketplace map, moves it, or takes it off.

        Its own verb, like `set_listing_visibility`, and for the same reason: it
        changes one thing that a customer can see and nothing the business runs
        on. A branch with no position is still bookable and still found by name
        or city; it is only absent from the map. Both `None` clears the pin.
        """
        validate_coordinates(latitude, longitude)
        location = await self.get_location(location_id)
        location.latitude = latitude
        location.longitude = longitude
        await self.locations.session.flush()
        return location

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

    def __init__(
        self, *, listings: PublicCatalogRepository, images: ImageStore | None = None
    ) -> None:
        self.listings = listings
        self.images = images

    async def covers_for(self, business_ids: list[UUID]) -> dict[UUID, BusinessPhoto]:
        return await self.listings.covers_for(business_ids)

    async def photos_for(self, business_id: UUID) -> list[BusinessPhoto]:
        return await self.listings.photos_for(business_id)

    async def read_public_photo(self, photo_id: UUID, variant: str) -> bytes | None:
        """A listed business's photo bytes, or None if there is no such photo
        to show the public (unknown, removed, or its business isn't listed)."""
        if self.images is None:
            raise RuntimeError("PublicCatalogService was built without photo storage.")
        photo = await self.listings.get_public_photo(photo_id)
        if photo is None:
            return None
        key = photo_storage_key(photo.storage_prefix, variant)
        return await asyncio.to_thread(self.images.read, key)

    async def search(
        self,
        *,
        term: str | None = None,
        city: str | None = None,
        category: str | None = None,
        bounding_box: tuple[float, float, float, float] | None = None,
        order: Literal["name", "rating"] = "name",
        limit: int = 20,
        offset: int = 0,
    ) -> list[ListingCard]:
        rows = await self.listings.search(
            term=term,
            city=city,
            category=category,
            bounding_box=bounding_box,
            order=order,
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
