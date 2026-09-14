"""media · CONTRACT layer — API boundary DTOs.

Layer rule: pydantic only. These are not the domain model and not the table.
"""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.schemas import ApiSchema
from app.modules.media.domain import MediaAssetKind


class RequestMediaUploadRequest(ApiSchema):
    business_id: UUID
    location_id: UUID | None = None
    kind: MediaAssetKind
    file_name: str = Field(max_length=255)
    content_type: str = Field(max_length=255)
    #: Upper bound enforced again in the domain against configuration; this is
    #: the cheap rejection before any work happens.
    size_bytes: int = Field(gt=0, le=100 * 1024 * 1024)


class MediaUploadResponse(ApiSchema):
    """docs/07 section 9.

    `upload_url` points at Nextcloud, not at this API — the browser PUTs there
    directly and the bytes never touch the application server.
    """

    asset_id: UUID
    upload_url: str
    webdav_path: str
    upload_token: str
    expires_at: datetime


class CompleteMediaUploadRequest(ApiSchema):
    upload_token: str = Field(max_length=64)


class MediaAssetOut(ApiSchema):
    id: UUID
    business_id: UUID
    location_id: UUID | None
    kind: MediaAssetKind
    file_name: str
    content_type: str
    size_bytes: int
    is_ready: bool
    is_public: bool
    created_at: datetime


class MediaLinkOut(ApiSchema):
    asset_id: UUID
    url: str
