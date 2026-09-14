"""media · DOMAIN layer — domain events."""

from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True)
class MediaUploadRequested(DomainEvent):
    tenant_id: UUID
    asset_id: UUID
    business_id: UUID
    kind: str


@dataclass(frozen=True)
class MediaAssetReady(DomainEvent):
    """The bytes are confirmed present. Only now may anything render it."""

    tenant_id: UUID
    asset_id: UUID
    business_id: UUID
    kind: str
