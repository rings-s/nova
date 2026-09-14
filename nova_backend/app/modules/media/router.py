"""media · DELIVERY layer — HTTP.

Layer rule: schemas, service, dependencies. No business rules here.

Note there is no upload endpoint that accepts a file body, and there must never
be one. The browser PUTs to Nextcloud directly (docs/02 section 4); this API
only issues and confirms authorisations. An `UploadFile` parameter here would
quietly move every salon's portfolio through the application server's memory.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.pagination import PageParams
from app.core.schemas import Page
from app.core.security import require_staff
from app.core.throttling import write_rate_limit
from app.modules.media.dependencies import get_media_service
from app.modules.media.domain import MediaAssetKind
from app.modules.media.schemas import (
    CompleteMediaUploadRequest,
    MediaAssetOut,
    MediaLinkOut,
    MediaUploadResponse,
    RequestMediaUploadRequest,
)
from app.modules.media.service import MediaService

router = APIRouter(prefix="/tenants/{tenant_id}/media", tags=["media"])


@router.post(
    "/uploads",
    response_model=MediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def request_upload(
    tenant_id: UUID,
    payload: RequestMediaUploadRequest,
    session: AsyncSession = Depends(get_db_session),
    service: MediaService = Depends(get_media_service),
) -> MediaUploadResponse:
    """Authorises one upload to one path. Staff only — this reserves storage."""
    authorisation = await service.request_upload(**payload.model_dump())
    await session.commit()
    return MediaUploadResponse(
        asset_id=authorisation.asset.id,
        upload_url=authorisation.upload_url,
        webdav_path=authorisation.asset.webdav_path,
        upload_token=authorisation.upload_token,
        expires_at=authorisation.expires_at,
    )


@router.post(
    "/uploads/{asset_id}/complete",
    response_model=MediaAssetOut,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def complete_upload(
    tenant_id: UUID,
    asset_id: UUID,
    payload: CompleteMediaUploadRequest,
    session: AsyncSession = Depends(get_db_session),
    service: MediaService = Depends(get_media_service),
) -> object:
    """Confirms the bytes landed, and makes the asset renderable."""
    asset = await service.complete_upload(asset_id, upload_token=payload.upload_token)
    await session.commit()
    return asset


@router.get("", response_model=Page[MediaAssetOut])
async def list_business_media(
    tenant_id: UUID,
    business_id: UUID,
    kind: MediaAssetKind | None = Query(default=None),
    params: PageParams = Depends(),
    service: MediaService = Depends(get_media_service),
) -> Page[MediaAssetOut]:
    assets = await service.list_for_business(
        business_id, kind=kind, limit=params.limit, offset=params.offset
    )
    return Page(items=[MediaAssetOut.model_validate(a) for a in assets])


@router.get("/{asset_id}", response_model=MediaAssetOut)
async def get_media_asset(
    tenant_id: UUID,
    asset_id: UUID,
    service: MediaService = Depends(get_media_service),
) -> object:
    return await service.get(asset_id)


@router.get("/{asset_id}/link", response_model=MediaLinkOut)
async def get_media_link(
    tenant_id: UUID,
    asset_id: UUID,
    service: MediaService = Depends(get_media_service),
) -> MediaLinkOut:
    """A shareable URL, generated on demand rather than stored."""
    return MediaLinkOut(asset_id=asset_id, url=await service.public_url(asset_id))


@router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def delete_media_asset(
    tenant_id: UUID,
    asset_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: MediaService = Depends(get_media_service),
) -> None:
    """Soft delete. The worker removes the binary afterwards (docs/08 s15)."""
    await service.soft_delete(asset_id)
    await session.commit()
