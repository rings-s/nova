from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.schemas import ApiSchema
from app.modules.identity.domain import MembershipRole


class TenantCreate(ApiSchema):
    name_en: str = Field(min_length=1, max_length=200)
    name_ar: str = Field(min_length=1, max_length=200)
    phone: str
    default_currency: str = Field(default="SAR", min_length=3, max_length=3)

    # No `owner_user_id`: ownership is taken from the authenticated principal.
    # Accepting it would let a caller create a business owned by someone else.


class TenantRead(ApiSchema):
    id: UUID
    name_en: str
    name_ar: str
    slug: str
    phone: str
    default_currency: str
    created_at: datetime
    updated_at: datetime


class CustomerCreate(ApiSchema):
    full_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(max_length=32)
    email: str | None = Field(default=None, max_length=255)
    preferred_language: str | None = Field(default=None, max_length=8)
    marketing_consent: bool = False
    whatsapp_consent: bool = False
    notes: str | None = Field(default=None, max_length=2000)


class CustomerUpdateConsent(ApiSchema):
    marketing_consent: bool | None = None
    whatsapp_consent: bool | None = None


class CustomerRead(ApiSchema):
    id: UUID
    tenant_id: UUID
    full_name: str
    phone: str
    email: str | None
    preferred_language: str
    marketing_consent: bool
    whatsapp_consent: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class MembershipCreate(ApiSchema):
    """Grant by email address, to an account that already exists.

    No `user_id`: an owner adding a colleague knows their email, not their
    internal id, and accepting an id would let a caller probe for valid ones.
    """

    email: str = Field(max_length=255)
    role: MembershipRole


class MembershipUpdateRole(ApiSchema):
    role: MembershipRole


class MembershipRead(ApiSchema):
    id: UUID
    tenant_id: UUID
    user_id: UUID
    # Denormalised from the linked account so a staff list is one request.
    # Never the password hash, the lockout counters, or the token version.
    email: str
    full_name: str
    role: MembershipRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
