"""call_center · DELIVERY layer — request and response shapes."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.schemas import ApiSchema


class CreatePhoneLineRequest(ApiSchema):
    business_id: UUID
    #: The Unifonic number, E.164: `+9668XXXXXXXX`.
    number_e164: str = Field(max_length=20)
    #: The language Sara greets in; she follows the caller after that.
    locale: str = Field(default="ar", max_length=8)


class PhoneLineOut(ApiSchema):
    id: UUID
    business_id: UUID
    number_e164: str
    locale: str
    agent_name: str
    is_active: bool
    created_at: datetime


class PhoneLineSetupOut(ApiSchema):
    line: PhoneLineOut
    #: Paste into the number's inbound application in the Unifonic console. It is
    #: the line's credential: rotate it if it leaks.
    answer_url: str


class CallOut(ApiSchema):
    id: UUID
    line_id: UUID
    business_id: UUID
    direction: str
    purpose: str
    status: str
    outcome: str | None
    caller_e164: str | None
    customer_id: UUID | None
    booking_id: UUID | None
    turns: int
    verified: bool
    started_at: datetime
    ended_at: datetime | None
