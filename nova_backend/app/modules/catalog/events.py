"""Domain events for the catalog module."""

from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True)
class BusinessCreated(DomainEvent):
    tenant_id: UUID
    business_id: UUID


@dataclass(frozen=True)
class LocationCreated(DomainEvent):
    tenant_id: UUID
    business_id: UUID
    location_id: UUID


@dataclass(frozen=True)
class ServicePublished(DomainEvent):
    tenant_id: UUID
    location_id: UUID
    service_id: UUID
