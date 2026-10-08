"""catalog · DELIVERY layer — HTTP.

Layer rule: may import schemas, service, dependencies.
Must not import models or repositories, and must contain no business rules.
Every handler here is: parse -> call one service method -> commit -> return.
"""

import time
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session
from app.core.pagination import PageParams
from app.core.schemas import Page
from app.core.security import purpose_key, require_staff
from app.core.throttling import default_rate_limit, write_rate_limit
from app.integrations.geocoding import ReverseGeocoder
from app.modules.booking.dependencies import get_booking_service
from app.modules.booking.service import BookingService
from app.modules.catalog.dependencies import (
    get_catalog_service,
    get_category_service,
    get_geocoder,
)
from app.modules.catalog.domain import (
    PHOTO_LINK_PURPOSE,
    PHOTO_LINK_TTL_SECONDS,
    PHOTO_VARIANTS,
    sign_photo_link,
)
from app.modules.catalog.exceptions import PhotoTooLargeError
from app.modules.catalog.models import BusinessPhoto
from app.modules.catalog.schemas import (
    AssignServiceRequest,
    BusinessOut,
    BusinessPhotoOut,
    CategoryAdminOut,
    CreateBusinessRequest,
    CreateCategoryRequest,
    CreateLocationRequest,
    CreateProviderRequest,
    CreateServiceRequest,
    LocationOut,
    PlaceOut,
    ProviderOut,
    ServiceOut,
    SetListingVisibilityRequest,
    SetLocationPositionRequest,
    UpdateCategoryRequest,
    UpdateLocationRequest,
    UpdatePhotoRequest,
    UpdateProviderRequest,
    UpdateServiceRequest,
)
from app.modules.catalog.service import CatalogService, CategoryService
from app.modules.identity.dependencies import RequirePermission, require_superuser
from app.modules.identity.domain import StaffPermission

# Every catalog route is nested under a tenant, so `get_tenant_context` can
# resolve tenant_id from the path and scope every repository (ADR-0003).
#
# Reads are open to any caller with tenant access, including a customer:
# browsing a salon's services is the point of the storefront. Every WRITE is
# staff-only, and more than that, owner or manager (`_MANAGE_CATALOG` below).
# Staff-only was previously implicit — nothing but staff could reach a
# tenant at all — and became load-bearing the moment customer principals
# could. An open `POST /services` lets a customer invent a 0.00 SAR service
# and book it; an open `POST /businesses` makes the globally-unique `slug`
# namespace squattable.
#: Every catalog write changes what the salon sells, at what price, where, or
#: whether it is advertised at all — owner and manager work, not the front
#: desk's (`StaffPermission.MANAGE_CATALOG`). Providers' working hours live in
#: `booking` and stay open to all staff.
_MANAGE_CATALOG = RequirePermission(StaffPermission.MANAGE_CATALOG)

router = APIRouter(prefix="/tenants/{tenant_id}/catalog", tags=["catalog"])


@router.post(
    "/businesses",
    response_model=BusinessOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def create_business(
    tenant_id: UUID,
    payload: CreateBusinessRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
) -> object:
    """Creates a business (a storefront) in this tenant. Owners and managers.

    Its URL slug comes from the English name and must be unique on NOVA. It is
    listed on the marketplace from the start; hide it with
    `PATCH /catalog/businesses/{business_id}/listing`."""
    business = await service.create_business(**payload.model_dump())
    await session.commit()
    return business


@router.get("/businesses", response_model=Page[BusinessOut], dependencies=[Depends(require_staff)])
async def list_businesses(
    tenant_id: UUID,
    params: PageParams = Depends(),
    service: CatalogService = Depends(get_catalog_service),
) -> Page[BusinessOut]:
    """This salon's storefronts, oldest first. Staff only.

    How a dashboard finds the business it manages on a device that never saw
    it being created — until this existed the id was only ever returned by
    the create call, so signing in on a new browser looked like having no
    business at all, and offered to create a duplicate.
    """
    rows = await service.list_businesses(limit=params.limit, offset=params.offset)
    return Page(items=[BusinessOut.model_validate(row) for row in rows])


@router.get(
    "/businesses/{business_id}", response_model=BusinessOut, dependencies=[Depends(require_staff)]
)
async def get_business(
    tenant_id: UUID,
    business_id: UUID,
    service: CatalogService = Depends(get_catalog_service),
) -> object:
    """One business in this tenant, with its rating average and count. Staff only.

    The marketplace's public view of a business is
    `GET /discovery/businesses/{slug}`."""
    return await service.get_business(business_id)


@router.patch(
    "/businesses/{business_id}/listing",
    response_model=BusinessOut,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def set_listing_visibility(
    tenant_id: UUID,
    business_id: UUID,
    payload: SetListingVisibilityRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
) -> object:
    """Shows or hides this business on the public marketplace (ADR-0010).

    Staff-only, and separate from any "deactivate" verb on purpose: docs/11
    section 8 hides the listing of a salon whose invoice is 21 days overdue
    while its calendar, queue and existing bookings keep working. This is the
    switch that does that and nothing more.
    """
    business = await service.set_listing_visibility(business_id, is_listed=payload.is_listed)
    await session.commit()
    return business


@router.post(
    "/locations",
    response_model=LocationOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def create_location(
    tenant_id: UUID,
    payload: CreateLocationRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
) -> object:
    """Adds a branch to a business. Owners and managers.

    Put it on the marketplace map with `PATCH /catalog/locations/{location_id}/position`."""
    location = await service.create_location(**payload.model_dump())
    await session.commit()
    return location


@router.patch(
    "/locations/{location_id}/position",
    response_model=LocationOut,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def set_location_position(
    tenant_id: UUID,
    location_id: UUID,
    payload: SetLocationPositionRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
) -> object:
    """Sets, moves or clears where a branch appears on the marketplace map.

    Staff-only. The map at `/discovery/map` reads this position (ADR-0012); a
    branch with none is absent from it but otherwise unaffected. Send both
    `latitude` and `longitude`, or both as null to remove the pin.
    """
    location = await service.set_location_position(
        location_id, latitude=payload.latitude, longitude=payload.longitude
    )
    await session.commit()
    return location


@router.patch(
    "/locations/{location_id}",
    response_model=LocationOut,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def update_location(
    tenant_id: UUID,
    location_id: UUID,
    payload: UpdateLocationRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
) -> object:
    """Renames a branch, or changes its city, timezone or whether it takes
    bookings (`is_active`). Owners and managers. Only the fields sent change."""
    location = await service.update_location(location_id, payload.changes())
    await session.commit()
    return location


@router.delete(
    "/locations/{location_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def delete_location(
    tenant_id: UUID,
    location_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
    bookings: BookingService = Depends(get_booking_service),
) -> None:
    """Deletes a branch, with its services and providers. Owners and managers.

    Refused with 409 `catalog_item_in_use` while an appointment there is still
    to come. Past bookings keep what they used."""
    await service.delete_location(location_id, has_upcoming=bookings.has_upcoming_bookings)
    await session.commit()


@router.get(
    "/businesses/{business_id}/locations",
    response_model=Page[LocationOut],
    dependencies=[Depends(require_staff)],
)
async def list_locations(
    tenant_id: UUID,
    business_id: UUID,
    service: CatalogService = Depends(get_catalog_service),
) -> Page[LocationOut]:
    """A business's branches, listed or not. Staff only: the public view is `/discovery`."""
    rows = await service.list_locations(business_id)
    return Page(items=[LocationOut.model_validate(r) for r in rows])


@router.get(
    "/places/reverse",
    response_model=PlaceOut,
    dependencies=[Depends(require_staff), Depends(_MANAGE_CATALOG), Depends(default_rate_limit)],
)
async def reverse_place(
    tenant_id: UUID,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    geocoder: ReverseGeocoder = Depends(get_geocoder),
) -> PlaceOut:
    """What the map calls a point: its district and city, in English and Arabic,
    and a branch name made from them. Owners and managers.

    The branch form calls this whenever its pin moves (detected, clicked or
    dragged) and fills its fields from the answer, so nothing is typed. From
    OpenStreetMap's Nominatim; 503 `geocoding_unavailable` when it does not
    answer, which is worth retrying."""
    place = await geocoder.reverse(latitude=latitude, longitude=longitude)
    area_en = place.district_en or place.city_en
    area_ar = place.district_ar or place.city_ar
    return PlaceOut(
        latitude=latitude,
        longitude=longitude,
        city_en=place.city_en,
        city_ar=place.city_ar,
        district_en=place.district_en,
        district_ar=place.district_ar,
        name_en=f"{area_en} branch" if area_en else None,
        name_ar=f"فرع {area_ar}" if area_ar else None,
    )


@router.post(
    "/services",
    response_model=ServiceOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def create_service(
    tenant_id: UUID,
    payload: CreateServiceRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
) -> object:
    """Adds a bookable service, with its duration and price, at one branch.
    Owners and managers.

    It has no availability until a provider is qualified for it
    (`POST /catalog/providers/{provider_id}/services`)."""
    created = await service.create_service(**payload.model_dump())
    await session.commit()
    return created


@router.patch(
    "/services/{service_id}",
    response_model=ServiceOut,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def update_service(
    tenant_id: UUID,
    service_id: UUID,
    payload: UpdateServiceRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
) -> object:
    """Changes a service's names, descriptions, category, duration, price, or
    whether it can be booked. Owners and managers. Only the fields sent change;
    bookings already made keep their price and times."""
    updated = await service.update_service(service_id, payload.changes())
    await session.commit()
    return updated


@router.delete(
    "/services/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def delete_service(
    tenant_id: UUID,
    service_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
    bookings: BookingService = Depends(get_booking_service),
) -> None:
    """Deletes a service. Owners and managers. Refused with 409
    `catalog_item_in_use` while an appointment for it is still to come."""
    await service.delete_service(service_id, has_upcoming=bookings.has_upcoming_bookings)
    await session.commit()


@router.get(
    "/locations/{location_id}/services",
    response_model=Page[ServiceOut],
    dependencies=[Depends(require_staff)],
)
async def list_services(
    tenant_id: UUID,
    location_id: UUID,
    service: CatalogService = Depends(get_catalog_service),
) -> Page[ServiceOut]:
    """The services offered at a branch. Staff only: the public view is `/discovery`."""
    rows = await service.list_services(location_id)
    return Page(items=[ServiceOut.model_validate(r) for r in rows])


@router.post(
    "/providers",
    response_model=ProviderOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def create_provider(
    tenant_id: UUID,
    payload: CreateProviderRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
) -> object:
    """Adds a provider, such as a stylist or therapist, at one branch. Owners and managers.

    Then set their working hours (`PUT /schedules/providers/{provider_id}`) and the
    services they perform (`POST /catalog/providers/{provider_id}/services`)."""
    provider = await service.create_provider(**payload.model_dump())
    await session.commit()
    return provider


@router.patch(
    "/providers/{provider_id}",
    response_model=ProviderOut,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def update_provider(
    tenant_id: UUID,
    provider_id: UUID,
    payload: UpdateProviderRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
) -> object:
    """Renames a provider, changes their title, or takes them off the booking
    list (`is_active`). Owners and managers. Only the fields sent change."""
    provider = await service.update_provider(provider_id, payload.changes())
    await session.commit()
    return provider


@router.delete(
    "/providers/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def delete_provider(
    tenant_id: UUID,
    provider_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
    bookings: BookingService = Depends(get_booking_service),
) -> None:
    """Deletes a provider. Owners and managers. Refused with 409
    `catalog_item_in_use` while they have an appointment still to come."""
    await service.delete_provider(provider_id, has_upcoming=bookings.has_upcoming_bookings)
    await session.commit()


@router.get(
    "/locations/{location_id}/providers",
    response_model=Page[ProviderOut],
    dependencies=[Depends(require_staff)],
)
async def list_providers(
    tenant_id: UUID,
    location_id: UUID,
    service: CatalogService = Depends(get_catalog_service),
) -> Page[ProviderOut]:
    """The providers working at a branch. Staff only."""
    rows = await service.list_providers(location_id)
    return Page(items=[ProviderOut.model_validate(r) for r in rows])


@router.post(
    "/providers/{provider_id}/services",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def assign_service_to_provider(
    tenant_id: UUID,
    provider_id: UUID,
    payload: AssignServiceRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
) -> None:
    """Qualifies a provider to perform a service. Owners and managers.

    The service must be at the provider's own branch (422
    `cross_location_assignment` otherwise). Qualifying the same pair twice answers
    409."""
    await service.assign_service_to_provider(provider_id, payload.service_id)
    await session.commit()


# --- Photos -----------------------------------------------------------------


def _photo_urls(photo: BusinessPhoto) -> dict[str, str]:
    """Signed links to each size of `photo`, served by discovery's public
    photo route. Signed rather than public so a business that isn't listed
    yet can still preview its own photos."""
    settings = get_settings()
    key = purpose_key(settings.secret_key, PHOTO_LINK_PURPOSE)
    expires = int(time.time()) + PHOTO_LINK_TTL_SECONDS
    tenant = str(photo.tenant_id)
    sig = sign_photo_link(photo_id=str(photo.id), tenant_id=tenant, expires=expires, key=key)
    query = urlencode({"t": tenant, "exp": expires, "sig": sig})
    return {
        variant: f"/api/v1/discovery/photos/{photo.id}/{variant}?{query}"
        for variant in sorted(PHOTO_VARIANTS)
    }


def _photo_out(photo: BusinessPhoto) -> BusinessPhotoOut:
    return BusinessPhotoOut(
        id=photo.id,
        business_id=photo.business_id,
        kind=photo.kind,
        position=photo.position,
        width=photo.width,
        height=photo.height,
        created_at=photo.created_at,
        urls=_photo_urls(photo),
    )


async def _read_capped(request: Request, limit: int) -> bytes:
    """The request body, refused as soon as it passes `limit` bytes — without
    ever holding more than that in memory."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise PhotoTooLargeError(limit)
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise PhotoTooLargeError(limit)
        chunks.append(chunk)
    return b"".join(chunks)


@router.get(
    "/businesses/{business_id}/photos",
    response_model=list[BusinessPhotoOut],
    dependencies=[Depends(require_staff)],
)
async def list_business_photos(
    tenant_id: UUID,
    business_id: UUID,
    service: CatalogService = Depends(get_catalog_service),
) -> list[BusinessPhotoOut]:
    """The cover and gallery, cover first, with preview links."""
    return [_photo_out(photo) for photo in await service.list_photos(business_id)]


@router.post(
    "/businesses/{business_id}/photos",
    response_model=BusinessPhotoOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                media: {"schema": {"type": "string", "format": "binary"}}
                for media in ("image/jpeg", "image/png", "image/webp")
            },
        }
    },
)
async def upload_business_photo(
    tenant_id: UUID,
    business_id: UUID,
    request: Request,
    kind: str = Query(default="gallery", pattern="^(cover|gallery)$"),
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
) -> BusinessPhotoOut:
    """Adds a photo: the raw image file as the request body (JPEG, PNG or
    WebP). `kind=cover` replaces any existing cover. The file is re-encoded
    before it is stored; see `integrations.images`."""
    data = await _read_capped(request, get_settings().media_max_upload_bytes)
    photo = await service.add_photo(business_id, kind=kind, data=data)
    await session.commit()
    return _photo_out(photo)


@router.patch(
    "/photos/{photo_id}",
    response_model=BusinessPhotoOut,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def update_business_photo(
    tenant_id: UUID,
    photo_id: UUID,
    payload: UpdatePhotoRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
) -> BusinessPhotoOut:
    """Makes a photo the cover (the old cover joins the gallery), moves the
    cover back into the gallery, or sets a gallery photo's `position`. Owners
    and managers."""
    photo = await service.update_photo(photo_id, kind=payload.kind, position=payload.position)
    await session.commit()
    return _photo_out(photo)


@router.delete(
    "/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_MANAGE_CATALOG), Depends(write_rate_limit)],
)
async def delete_business_photo(
    tenant_id: UUID,
    photo_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: CatalogService = Depends(get_catalog_service),
) -> None:
    """Deletes a photo and its stored files. Owners and managers."""
    await service.delete_photo(photo_id)
    await session.commit()


# --- Categories (platform-wide, superuser only) -------------------------------

#: Not under a tenant: the category list is shared by every salon, so no salon
#: role may change it. Tenants read it at `GET /discovery/categories`.
admin_router = APIRouter(
    prefix="/admin/catalog/categories",
    tags=["admin"],
    dependencies=[Depends(require_superuser)],
)


@admin_router.get("", response_model=list[CategoryAdminOut])
async def admin_list_categories(
    service: CategoryService = Depends(get_category_service),
) -> list[CategoryAdminOut]:
    """Every service category, retired ones included. NOVA administrators only."""
    rows = await service.list_categories(include_inactive=True)
    return [CategoryAdminOut.model_validate(row) for row in rows]


@admin_router.post(
    "",
    response_model=CategoryAdminOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(write_rate_limit)],
)
async def admin_create_category(
    payload: CreateCategoryRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CategoryService = Depends(get_category_service),
) -> object:
    """Adds a service category that every salon can file services under.
    NOVA administrators only.

    Its slug comes from the English name and never changes (409
    `duplicate_slug` if taken)."""
    category = await service.create(**payload.model_dump())
    await session.commit()
    return category


@admin_router.patch(
    "/{category_id}",
    response_model=CategoryAdminOut,
    dependencies=[Depends(write_rate_limit)],
)
async def admin_update_category(
    category_id: UUID,
    payload: UpdateCategoryRequest,
    session: AsyncSession = Depends(get_db_session),
    service: CategoryService = Depends(get_category_service),
) -> object:
    """Renames a category, or retires (`is_active: false`) or restores it.
    NOVA administrators only.

    A retired category can't be chosen for a new service and leaves the
    marketplace filter; services already filed under it keep it."""
    category = await service.update(category_id, **payload.model_dump(exclude_unset=True))
    await session.commit()
    return category
