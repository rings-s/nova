"""media · APPLICATION layer — use cases.

Layer rule: domain, repository, events, integrations, and other modules'
*services*. Must not import fastapi or another module's models/repository.

Services flush, never commit. The router owns the transaction boundary.

The upload flow, and why it has three steps:

    1. `request_upload`  the API validates, reserves an asset row, and returns
                         a URL plus a signed authorisation
    2. the BROWSER       PUTs the bytes straight to Nextcloud
    3. `complete_upload` the client tells us it landed; we verify against
                         storage and mark the asset ready

Step 2 not passing through FastAPI is the entire design (docs/02 section 4).
Step 3 verifying rather than trusting is what stops a client marking an asset
ready that was never uploaded.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.events import publish_event
from app.integrations.storage.nextcloud import MediaStorage
from app.modules.catalog.service import CatalogService
from app.modules.media.domain import (
    MediaAssetKind,
    assert_path_belongs_to_tenant,
    build_webdav_path,
    sanitize_file_name,
    sign_upload_authorisation,
    upload_expiry,
    validate_content_type,
    validate_size,
    verify_upload_authorisation,
)
from app.modules.media.events import MediaAssetReady, MediaUploadRequested
from app.modules.media.exceptions import MediaAssetNotFoundError, MediaNotUploadedError
from app.modules.media.models import MediaAssetRecord
from app.modules.media.repository import MediaAssetRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadAuthorisation:
    """Everything the browser needs to upload, and nothing more."""

    asset: MediaAssetRecord
    upload_url: str
    upload_token: str
    expires_at: datetime


class MediaService:
    def __init__(
        self,
        *,
        repository: MediaAssetRepository,
        storage: MediaStorage,
        catalog: CatalogService,
        tenant_id: UUID,
        secret_key: str,
        root_folder: str = "nova-media",
        upload_ttl_seconds: int = 900,
        max_upload_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.catalog = catalog
        self.tenant_id = tenant_id
        self.secret_key = secret_key
        self.root_folder = root_folder
        self.upload_ttl_seconds = upload_ttl_seconds
        self.max_upload_bytes = max_upload_bytes

    @property
    def session(self):
        return self.repository.session

    async def request_upload(
        self,
        *,
        business_id: UUID,
        kind: MediaAssetKind,
        file_name: str,
        content_type: str,
        size_bytes: int,
        location_id: UUID | None = None,
        now: datetime | None = None,
    ) -> UploadAuthorisation:
        """Reserves an asset and authorises one upload to one exact path."""
        now = now or datetime.now(UTC)

        # Tenant-scoped: a business id belonging to another salon is simply not
        # found, so an upload cannot be filed under someone else's storefront.
        await self.catalog.get_business(business_id)
        if location_id is not None:
            await self.catalog.get_location(location_id)

        content_type = validate_content_type(content_type)
        validate_size(size_bytes, max_bytes=self.max_upload_bytes)
        safe_name = sanitize_file_name(file_name, content_type=content_type)

        asset_id = uuid4()
        webdav_path = build_webdav_path(
            tenant_id=self.tenant_id,
            business_id=business_id,
            kind=kind,
            asset_id=asset_id,
            file_name=safe_name,
            root=self.root_folder,
        )
        expires_at = upload_expiry(now=now, ttl_seconds=self.upload_ttl_seconds)

        asset = MediaAssetRecord(
            id=asset_id,
            tenant_id=self.tenant_id,
            business_id=business_id,
            location_id=location_id,
            kind=kind,
            file_name=safe_name,
            content_type=content_type,
            size_bytes=size_bytes,
            webdav_path=webdav_path,
            is_ready=False,
            upload_expires_at=expires_at,
        )
        self.repository.add(asset)
        await self.repository.session.flush()

        # Best-effort: a missing folder is not worth failing the request over,
        # and the PUT will surface a real storage problem anyway.
        folder_path = webdav_path.rsplit("/", 1)[0]
        try:
            await self.storage.ensure_folder(folder_path=folder_path)
        except Exception:
            logger.warning(
                "nextcloud_ensure_folder_failed", extra={"folder": folder_path}, exc_info=True
            )

        await publish_event(
            self.session,
            MediaUploadRequested(
                tenant_id=self.tenant_id,
                asset_id=asset.id,
                business_id=business_id,
                kind=str(kind),
            ),
        )

        return UploadAuthorisation(
            asset=asset,
            upload_url=self.storage.upload_url_for(webdav_path=webdav_path),
            upload_token=sign_upload_authorisation(
                asset_id=asset.id,
                tenant_id=self.tenant_id,
                webdav_path=webdav_path,
                expires_at=expires_at,
                secret=self.secret_key,
            ),
            expires_at=expires_at,
        )

    async def complete_upload(
        self,
        asset_id: UUID,
        *,
        upload_token: str,
        verify_with_storage: bool = True,
        now: datetime | None = None,
    ) -> MediaAssetRecord:
        """Marks an asset ready, after checking the bytes are actually there.

        The signed token proves the server authorised this path, and the
        storage check proves something was written. Skipping either would let a
        client publish an asset that renders as a broken image forever.
        """
        now = now or datetime.now(UTC)
        asset = await self.get(asset_id)

        assert_path_belongs_to_tenant(
            asset.webdav_path, tenant_id=self.tenant_id, root=self.root_folder
        )
        verify_upload_authorisation(
            upload_token,
            asset_id=asset.id,
            tenant_id=self.tenant_id,
            webdav_path=asset.webdav_path,
            expires_at=asset.upload_expires_at or now,
            secret=self.secret_key,
            now=now,
        )

        if verify_with_storage:
            try:
                if not await self.storage.exists(webdav_path=asset.webdav_path):
                    raise MediaNotUploadedError(asset_id)
            except MediaNotUploadedError:
                raise
            except Exception:
                # Storage unreachable is an infrastructure failure, not a
                # client error: better to leave the asset un-ready and let the
                # client retry than to publish an unverified one.
                logger.warning(
                    "nextcloud_verify_failed", extra={"asset_id": str(asset_id)}, exc_info=True
                )
                raise

        asset.is_ready = True
        asset.upload_expires_at = None
        await self.repository.session.flush()

        await publish_event(
            self.session,
            MediaAssetReady(
                tenant_id=self.tenant_id,
                asset_id=asset.id,
                business_id=asset.business_id,
                kind=str(asset.kind),
            ),
        )
        return asset

    async def get(self, asset_id: UUID) -> MediaAssetRecord:
        asset = await self.repository.get(asset_id)
        if asset is None:
            raise MediaAssetNotFoundError(asset_id)
        return asset

    async def list_for_business(
        self,
        business_id: UUID,
        *,
        kind: MediaAssetKind | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MediaAssetRecord]:
        await self.catalog.get_business(business_id)
        return await self.repository.list_for_business(
            business_id, kind=kind, limit=limit, offset=offset
        )

    async def public_url(self, asset_id: UUID, *, expires_days: int = 7) -> str:
        """A shareable link for a ready asset.

        Generated on demand through the storage adapter rather than stored:
        docs/07 section 9 wants public URLs to come from a controlled proxy or
        signed link, and a URL persisted in Postgres outlives whatever policy
        created it.
        """
        asset = await self.get(asset_id)
        if not asset.is_ready:
            raise MediaNotUploadedError(asset_id)
        assert_path_belongs_to_tenant(
            asset.webdav_path, tenant_id=self.tenant_id, root=self.root_folder
        )
        return await self.storage.create_share_link(
            webdav_path=asset.webdav_path, expires_days=expires_days
        )

    async def soft_delete(self, asset_id: UUID, *, now: datetime | None = None) -> None:
        """Retires an asset. The binary is removed later, by the worker.

        docs/08 section 15: soft delete first, then a background hard delete.
        Deleting the row and the file in one request means a failed storage
        call leaves a dangling reference — or worse, deletes a file a catalog
        row still points at.
        """
        asset = await self.get(asset_id)
        asset.mark_deleted(now=now or datetime.now(UTC))
        await self.repository.session.flush()

    async def purge_deleted(self, asset: MediaAssetRecord) -> None:
        """Hard-deletes the binary for an already soft-deleted asset."""
        assert_path_belongs_to_tenant(
            asset.webdav_path, tenant_id=asset.tenant_id, root=self.root_folder
        )
        await self.storage.delete(webdav_path=asset.webdav_path)


__all__ = ["MediaService", "UploadAuthorisation"]
