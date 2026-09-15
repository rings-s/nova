from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.core.schemas import ApiSchema
from app.core.validators import validate_email
from app.modules.identity.domain import MembershipRole


class CreateTenantRequest(ApiSchema):
    name_en: str = Field(min_length=1, max_length=200)
    name_ar: str = Field(min_length=1, max_length=200)
    phone: str
    default_currency: str = Field(default="SAR", min_length=3, max_length=3)

    # No `owner_user_id`: ownership is taken from the authenticated principal.
    # Accepting it would let a caller create a business owned by someone else.


class TenantOut(ApiSchema):
    id: UUID
    name_en: str
    name_ar: str
    slug: str
    phone: str
    default_currency: str
    created_at: datetime
    updated_at: datetime


class CreateCustomerRequest(ApiSchema):
    full_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(max_length=32)
    email: str | None = Field(default=None, max_length=255)
    preferred_language: str | None = Field(default=None, max_length=8)
    marketing_consent: bool = False
    whatsapp_consent: bool = False
    notes: str | None = Field(default=None, max_length=2000)


class UpdateCustomerConsentRequest(ApiSchema):
    marketing_consent: bool | None = None
    whatsapp_consent: bool | None = None


class CustomerOut(ApiSchema):
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


class CreateMembershipRequest(ApiSchema):
    """Starts an invite to `email`, for whoever redeems its token.

    No `user_id`: an owner adding a colleague knows their email, not their
    internal id, and accepting an id would let a caller probe for valid ones.
    `email` is the inviter's own record of intent — never checked against
    whoever accepts (docs/14 TM-04).
    """

    email: str = Field(max_length=255)
    role: MembershipRole


class MembershipInviteOut(ApiSchema):
    """The invite, plus its one-time token.

    `token` is returned here and nowhere else — only its hash is stored.
    Relaying it to the actual person is the inviter's job.
    """

    id: UUID
    tenant_id: UUID
    email: str
    role: MembershipRole
    token: str
    expires_at: datetime
    created_at: datetime


class MembershipInviteSummary(ApiSchema):
    """A pending invite, listed without its token."""

    id: UUID
    tenant_id: UUID
    email: str
    role: MembershipRole
    expires_at: datetime
    created_at: datetime


class AcceptInviteRequest(ApiSchema):
    token: str = Field(min_length=1, max_length=128)


class UpdateMembershipRoleRequest(ApiSchema):
    role: MembershipRole


class MembershipOut(ApiSchema):
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


# --- Authentication -------------------------------------------------------


class RegisterRequest(ApiSchema):
    email: str = Field(max_length=255)
    password: str = Field(min_length=12, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    phone: str | None = None

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return validate_email(value)


class LoginRequest(ApiSchema):
    email: str = Field(max_length=255)
    password: str = Field(max_length=200)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return validate_email(value)


class RefreshRequest(ApiSchema):
    refresh_token: str


class ConfirmPhoneVerificationRequest(ApiSchema):
    #: The purpose-signed JWT `request_phone_verification` sent over WhatsApp
    #: (`security.issue_purpose_token`), not a typed-in code. A generous cap
    #: rather than none: request bodies have no size limit yet (docs/14
    #: TM-10), so an unbounded string field is a small, free thing to bound.
    token: str = Field(min_length=1, max_length=4096)


class TokenOut(ApiSchema):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class UserOut(ApiSchema):
    id: str
    email: str
    full_name: str
