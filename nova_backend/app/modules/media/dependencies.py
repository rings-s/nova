"""media · DELIVERY layer — DI providers."""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session, get_tenant_context
from app.integrations.storage.nextcloud import MediaStorage, build_media_storage
from app.modules.catalog.dependencies import build_catalog_service, get_catalog_service
from app.modules.catalog.service import CatalogService
from app.modules.media.repository import MediaAssetRepository
from app.modules.media.service import MediaService


def get_media_storage() -> MediaStorage:
    """The live adapter when credentials exist, otherwise the placeholder."""
    settings = get_settings()
    return build_media_storage(
        base_url=settings.nextcloud_url,
        username=settings.nextcloud_username,
        app_password=settings.nextcloud_app_password,
    )


def build_media_service(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    storage: MediaStorage | None = None,
    catalog: CatalogService | None = None,
) -> MediaService:
    """Assembles the service outside the request DI graph (worker, webhooks)."""
    settings = get_settings()
    return MediaService(
        repository=MediaAssetRepository(session, tenant_id),
        storage=storage or get_media_storage(),
        catalog=catalog or build_catalog_service(session, tenant_id),
        tenant_id=tenant_id,
        secret_key=settings.secret_key,
        root_folder=settings.nextcloud_root_folder,
        upload_ttl_seconds=settings.media_upload_url_ttl_seconds,
        max_upload_bytes=settings.media_max_upload_bytes,
    )


def get_media_service(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: UUID = Depends(get_tenant_context),
    storage: MediaStorage = Depends(get_media_storage),
    catalog: CatalogService = Depends(get_catalog_service),
) -> MediaService:
    return build_media_service(session, tenant_id, storage=storage, catalog=catalog)
