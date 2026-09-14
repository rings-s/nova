"""queue · CONTRACT layer — API boundary DTOs.

Layer rule: pydantic only. These are not the domain model and not the table.
"""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.schemas import ApiSchema
from app.modules.queue.domain import QueueEntrySource, QueueEntryStatus, TicketStatus


class CreateQueueRequest(ApiSchema):
    location_id: UUID
    name_en: str = Field(default="Main Queue", max_length=255)
    name_ar: str = Field(default="الطابور الرئيسي", max_length=255)
    average_service_minutes: int = Field(default=30, ge=5, le=480)


class QueueOut(ApiSchema):
    id: UUID
    tenant_id: UUID
    location_id: UUID
    name_en: str
    name_ar: str
    is_open: bool
    average_service_minutes: int


class SetQueueOpenRequest(ApiSchema):
    is_open: bool


class JoinQueueRequest(ApiSchema):
    service_id: UUID
    provider_id: UUID | None = None
    party_size: int = Field(default=1, ge=1, le=20)

    #: Set when an already-booked customer arrives, so their appointment and
    #: the walk-ins share one timeline instead of two competing lists.
    booking_id: UUID | None = None

    #: Staff only, same rule as booking: a customer joins only for themselves.
    on_behalf_of_customer_id: UUID | None = None


class QueueEntryOut(ApiSchema):
    id: UUID
    queue_id: UUID
    location_id: UUID
    customer_id: UUID
    service_id: UUID
    provider_id: UUID | None
    status: QueueEntryStatus
    source: QueueEntrySource
    position: int
    party_size: int
    booking_id: UUID | None
    joined_at: datetime | None
    called_at: datetime | None

    #: Place in the line as the customer experiences it (1 = next), which is
    #: not `position` — that is a monotonic join counter that never renumbers.
    place_in_line: int | None = None
    estimated_wait_minutes: int | None = None


class IssueTicketRequest(ApiSchema):
    booking_id: UUID | None = None
    queue_entry_id: UUID | None = None


class TicketOut(ApiSchema):
    """docs/07 section 7.

    `qr_payload` is returned exactly once, at issue. Only its hash is stored,
    so it cannot be fetched again later — reception reissues instead.
    """

    id: UUID
    ticket_code: str
    qr_payload: str
    status: TicketStatus
    expires_at: datetime
    ticket_page_url: str


class TicketStateOut(ApiSchema):
    """A ticket without its secret, for status checks after issue."""

    id: UUID
    ticket_code: str
    status: TicketStatus
    expires_at: datetime
    redeemed_at: datetime | None
    booking_id: UUID | None
    queue_entry_id: UUID | None


class CheckInTicketRequest(ApiSchema):
    """What the reception scanner posts.

    A single opaque payload rather than docs/07's `ticket_id` + `qr_token`
    pair: the scanner reads one string out of the QR image, and splitting it
    client-side is an invitation to submit a mismatched pair.
    """

    qr_payload: str = Field(max_length=512)


class CheckInResultOut(ApiSchema):
    ticket: TicketStateOut
    entry: QueueEntryOut | None = None
