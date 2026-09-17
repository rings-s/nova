from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.core.schemas import ApiSchema


class CreateBusinessRequest(ApiSchema):
    name_en: str = Field(min_length=1, max_length=255)
    name_ar: str = Field(min_length=1, max_length=255)
    description_en: str | None = None
    description_ar: str | None = None


class BusinessOut(ApiSchema):
    id: UUID
    tenant_id: UUID
    name_en: str
    name_ar: str
    slug: str
    description_en: str | None
    description_ar: str | None
    is_active: bool
    #: Whether this business is advertised on the public marketplace.
    is_listed: bool
    created_at: datetime
    updated_at: datetime


class SetListingVisibilityRequest(ApiSchema):
    is_listed: bool


class CreateLocationRequest(ApiSchema):
    business_id: UUID
    name_en: str = Field(min_length=1, max_length=255)
    name_ar: str = Field(min_length=1, max_length=255)
    phone: str
    timezone: str = "Asia/Riyadh"
    #: Used by marketplace search. Optional, but a branch without one cannot be
    #: found by a city filter — only by name or map radius.
    city: str | None = Field(default=None, max_length=120)
    latitude: float | None = None
    longitude: float | None = None


class LocationOut(ApiSchema):
    id: UUID
    tenant_id: UUID
    business_id: UUID
    name_en: str
    name_ar: str
    slug: str
    phone: str
    timezone: str
    city: str | None
    latitude: float | None
    longitude: float | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CreateServiceRequest(ApiSchema):
    location_id: UUID
    name_en: str = Field(min_length=1, max_length=255)
    name_ar: str = Field(min_length=1, max_length=255)
    description_en: str | None = None
    description_ar: str | None = None
    category: str | None = Field(default=None, max_length=120)
    duration_minutes: int = Field(gt=0)
    price: Decimal = Field(ge=0)
    currency: str = Field(default="SAR", min_length=3, max_length=3)


class ServiceOut(ApiSchema):
    id: UUID
    tenant_id: UUID
    location_id: UUID
    name_en: str
    name_ar: str
    description_en: str | None
    description_ar: str | None
    category: str | None
    duration_minutes: int
    price: Decimal
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CreateProviderRequest(ApiSchema):
    location_id: UUID
    name_en: str = Field(min_length=1, max_length=255)
    name_ar: str = Field(min_length=1, max_length=255)
    title_en: str | None = Field(default=None, max_length=255)
    title_ar: str | None = Field(default=None, max_length=255)


class ProviderOut(ApiSchema):
    id: UUID
    tenant_id: UUID
    location_id: UUID
    name_en: str
    name_ar: str
    title_en: str | None
    title_ar: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AssignServiceRequest(ApiSchema):
    service_id: UUID
