"""catalog · DELIVERY layer — HTTP.

Layer rule: may import schemas, service, dependencies.
Must not import models or repositories, and must contain no business rules.
Every handler here is: parse -> call one service method -> commit -> return.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.schemas import Page
from app.core.throttling import write_rate_limit
from app.modules.catalog.dependencies import get_catalog_service
from app.modules.catalog.schemas import (
    AssignServiceRequest,
    BusinessOut,
    CreateBusinessRequest,
    CreateLocationRequest,
    CreateProviderRequest,
    CreateServiceRequest,
    LocationOut,
    ProviderOut,
    ServiceOut,
    SetListingVisibilityRequest,
    SetLocationPositionRequest,
)
from app.modules.catalog.service import CatalogService
from app.modules.identity.dependencies import RequirePermission
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
    business = await service.create_business(**payload.model_dump())
    await session.commit()
    return business


@router.get("/businesses/{business_id}", response_model=BusinessOut)
async def get_business(
    tenant_id: UUID,
    business_id: UUID,
    service: CatalogService = Depends(get_catalog_service),
) -> object:
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


@router.get("/businesses/{business_id}/locations", response_model=Page[LocationOut])
async def list_locations(
    tenant_id: UUID,
    business_id: UUID,
    service: CatalogService = Depends(get_catalog_service),
) -> Page[LocationOut]:
    rows = await service.list_locations(business_id)
    return Page(items=[LocationOut.model_validate(r) for r in rows])


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
    created = await service.create_service(**payload.model_dump())
    await session.commit()
    return created


@router.get("/locations/{location_id}/services", response_model=Page[ServiceOut])
async def list_services(
    tenant_id: UUID,
    location_id: UUID,
    service: CatalogService = Depends(get_catalog_service),
) -> Page[ServiceOut]:
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
    provider = await service.create_provider(**payload.model_dump())
    await session.commit()
    return provider


@router.get("/locations/{location_id}/providers", response_model=Page[ProviderOut])
async def list_providers(
    tenant_id: UUID,
    location_id: UUID,
    service: CatalogService = Depends(get_catalog_service),
) -> Page[ProviderOut]:
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
    await service.assign_service_to_provider(provider_id, payload.service_id)
    await session.commit()
