"""booking · CONTRACT layer — API boundary DTOs.

Layer rule: pydantic only. These are not the domain model and not the table.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from app.core.schemas import ApiSchema
from app.modules.booking.domain import MINUTES_PER_DAY, BookingSource, BookingStatus


class CreateBookingRequest(ApiSchema):
    location_id: UUID
    service_id: UUID
    provider_id: UUID
    starts_at: datetime
    #: Which channel brought this booking (docs/11 section 4). Optional, and
    #: only partly trusted: `resolve_booking_source` rejects a source the caller
    #: is not entitled to declare and overrides it entirely for staff booking on
    #: behalf. Omitted means `direct_link`, the zero-commission default.
    source: BookingSource | None = None
    notes: str | None = Field(default=None, max_length=1000)

    #: Returned by `POST /bookings/holds`. Supplying it converts that hold
    #: instead of racing for the slot again.
    hold_token: str | None = Field(default=None, max_length=64)
    #: Signed id from the availability response. When present it is verified,
    #: which is what stops an agent booking a slot the server never offered.
    slot_id: str | None = Field(default=None, max_length=64)

    #: Returned by `POST /discovery/businesses/{slug}/referrals` when the
    #: customer opened this salon's listing on the NOVA marketplace. Presenting
    #: it is what makes the booking `marketplace` rather than `direct_link`.
    #:
    #: Note this is not the client *declaring* a source — `resolve_booking_source`
    #: still refuses that (ADR-0008). It is the client presenting a credential
    #: NOVA issued, which the server looks up, checks against this business, and
    #: checks against the 30-day window before it changes anything.
    referral_token: str | None = Field(default=None, max_length=128)

    #: Staff only. Reception booking on behalf of a walk-in customer.
    #: A customer principal supplying this is rejected with 403 — otherwise
    #: anyone could create bookings in someone else's name.
    on_behalf_of_customer_id: UUID | None = None

    # No `customer_id`: the customer is taken from the authenticated principal,
    # never the request body.
    #
    # No `ends_at`: the slot end is derived from the service's own duration so
    # a client cannot request a 5-minute slot for a 90-minute treatment.


class CancelBookingRequest(ApiSchema):
    reason: str | None = Field(default=None, max_length=500)


class RescheduleBookingRequest(ApiSchema):
    new_starts_at: datetime
    #: Optional: move to a different provider at the same location.
    provider_id: UUID | None = None


class BookingOut(ApiSchema):
    id: UUID
    tenant_id: UUID
    business_id: UUID
    location_id: UUID
    service_id: UUID
    provider_id: UUID
    customer_id: UUID
    starts_at: datetime
    ends_at: datetime
    price: Decimal
    currency: str
    status: BookingStatus
    source: BookingSource
    cancellation_reason: str | None
    notes: str | None = None


class AvailabilityFilter(ApiSchema):
    provider_id: UUID
    service_id: UUID
    date_from: datetime
    date_to: datetime


class AvailableSlotOut(ApiSchema):
    """One bookable slot.

    `slot_id` is a deterministic HMAC over (tenant, provider, service, start),
    per docs/07 section 5. It contains no PII and cannot be forged without the
    server secret.
    """

    slot_id: str
    provider_id: UUID
    location_id: UUID
    service_id: UUID
    starts_at: datetime
    ends_at: datetime
    remaining_capacity: int = 1


class HoldSlotRequest(ApiSchema):
    provider_id: UUID
    service_id: UUID
    starts_at: datetime
    slot_id: str | None = Field(default=None, max_length=64)


class HoldSlotResult(ApiSchema):
    """Named `Result`, per the docs/07 section 1 naming table."""

    hold_token: str
    provider_id: UUID
    service_id: UUID
    starts_at: datetime
    ends_at: datetime
    expires_at: datetime


class WorkingWindowIn(ApiSchema):
    #: Monday = 0, matching `datetime.weekday()`.
    weekday: int = Field(ge=0, le=6)
    start_minute: int = Field(ge=0, lt=MINUTES_PER_DAY)
    end_minute: int = Field(gt=0, le=MINUTES_PER_DAY)

    @model_validator(mode="after")
    def _end_after_start(self) -> "WorkingWindowIn":
        if self.end_minute <= self.start_minute:
            raise ValueError("end_minute must be after start_minute")
        return self


class SetScheduleRequest(ApiSchema):
    """Replaces a provider's whole week.

    Deliberately not a partial update: omitting a weekday means "not working",
    which a merge could not express.
    """

    windows: list[WorkingWindowIn]


class ScheduleOut(ApiSchema):
    provider_id: UUID
    windows: list[WorkingWindowIn]


class ScheduleExceptionRequest(ApiSchema):
    on_date: date
    is_closed: bool = True
    start_minute: int | None = Field(default=None, ge=0, lt=MINUTES_PER_DAY)
    end_minute: int | None = Field(default=None, gt=0, le=MINUTES_PER_DAY)
    reason: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _open_windows_need_times(self) -> "ScheduleExceptionRequest":
        if not self.is_closed and (self.start_minute is None or self.end_minute is None):
            raise ValueError("An open exception needs both start_minute and end_minute")
        return self


class ScheduleExceptionOut(ApiSchema):
    id: UUID
    provider_id: UUID
    on_date: date
    is_closed: bool
    start_minute: int | None
    end_minute: int | None
    reason: str | None
