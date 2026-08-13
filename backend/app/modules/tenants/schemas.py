from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TenantCreate(BaseModel):
    name_en: str = Field(min_length=1, max_length=200)
    name_ar: str = Field(min_length=1, max_length=200)
    phone: str
    default_currency: str = Field(default="SAR", min_length=3, max_length=3)


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name_en: str
    name_ar: str
    slug: str
    phone: str
    default_currency: str
    created_at: datetime
    updated_at: datetime


class BranchCreate(BaseModel):
    name_en: str = Field(min_length=1, max_length=200)
    name_ar: str = Field(min_length=1, max_length=200)
    phone: str
    timezone: str = Field(default="Asia/Riyadh")


class BranchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name_en: str
    name_ar: str
    slug: str
    phone: str
    timezone: str
    created_at: datetime
    updated_at: datetime
