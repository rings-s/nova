"""booking · DOMAIN layer — the rules.

Layer rule: stdlib, pydantic, and `app.core` values/exceptions only.
Must not import fastapi or sqlalchemy. Nothing here knows a database exists.

This module defines a rich entity rather than validator functions, because a
booking has a lifecycle that can be corrupted: a booking that reached
COMPLETED without ever being CHECKED_IN is not merely invalid input, it is a
broken aggregate. The transitions below are the only legal way to move it.

State machine (docs/06 section 4):

    DRAFT ──▶ PENDING_PAYMENT ──▶ CONFIRMED ──▶ CHECKED_IN ──▶ IN_SERVICE ──▶ COMPLETED
      │              │                │
      └──────────────┴────────────────┼──▶ CANCELLED
                                      └──▶ NO_SHOW
"""

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from itertools import pairwise
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.exceptions import ConflictError, ValidationDomainError
from app.core.values import Money, TimeRange


class BookingStatus(StrEnum):
    DRAFT = "draft"
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    IN_SERVICE = "in_service"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class BookingSource(StrEnum):
    """Which channel brought this booking (docs/11 section 4).

    This is not a UI label. It is the fact that decides whether NOVA may charge
    commission on the booking, so it is captured once at creation and is
    immutable thereafter — no transition, reschedule, or staff edit changes it.

    The values it replaced (`pwa`, `staff`, `whatsapp`, `ai_agent`) described
    the *interface* a booking arrived through, which cannot answer the only
    question billing asks: did NOVA introduce this customer, or did the salon
    already have them? `pwa` in particular covered both the marketplace listing
    and the salon's own booking page — the two sides of that question — so it
    could never be split apart after the fact. See ADR-0008.

    `AI_AGENT` is listed because docs/11 lists it, but an agent should pass
    through the channel it was reached on rather than flattening a WhatsApp
    conversation into `ai_agent`; docs/11 section 4 says as much. Treat a
    stored `AI_AGENT` as an unattributed booking, which is why it sits in
    `NEVER_BILLABLE_SOURCES` below.
    """

    MARKETPLACE = "marketplace"  # NOVA discovery, search, or listing
    DIRECT_LINK = "direct_link"  # the business's own booking page
    WHATSAPP = "whatsapp"  # the business's WhatsApp number
    WALK_IN = "walk_in"  # queue ticket at the counter
    RECEPTION = "reception"  # staff booked on behalf of the customer
    AI_AGENT = "ai_agent"  # inherits the channel it was reached on


#: Sources that can never produce a billable commission line, whatever the
#: customer's history (docs/11 section 3 rules 2-3, and section 9 "Free
#: Forever"). Only `MARKETPLACE` is ever chargeable, and even then only on a
#: customer's first completed booking with that business.
#:
#: Stated here rather than in a future billing module so the invariant lives
#: next to the enum it constrains and can be asserted by a test today.
NEVER_BILLABLE_SOURCES: frozenset[BookingSource] = frozenset(
    {
        BookingSource.DIRECT_LINK,
        BookingSource.WHATSAPP,
        BookingSource.WALK_IN,
        BookingSource.RECEPTION,
        BookingSource.AI_AGENT,
    }
)


#: Statuses that still occupy the provider's calendar. A new booking may not
#: overlap an existing booking in one of these. Terminal statuses
#: (CANCELLED, NO_SHOW, COMPLETED) free the slot.
BLOCKING_STATUSES: frozenset[BookingStatus] = frozenset(
    {
        BookingStatus.DRAFT,
        BookingStatus.PENDING_PAYMENT,
        BookingStatus.CONFIRMED,
        BookingStatus.CHECKED_IN,
        BookingStatus.IN_SERVICE,
    }
)

#: The single source of truth for legal transitions. Adding a status means
#: adding it here — the entity has no other way to move.
_ALLOWED_TRANSITIONS: dict[BookingStatus, frozenset[BookingStatus]] = {
    BookingStatus.DRAFT: frozenset(
        {BookingStatus.PENDING_PAYMENT, BookingStatus.CONFIRMED, BookingStatus.CANCELLED}
    ),
    BookingStatus.PENDING_PAYMENT: frozenset({BookingStatus.CONFIRMED, BookingStatus.CANCELLED}),
    BookingStatus.CONFIRMED: frozenset(
        {BookingStatus.CHECKED_IN, BookingStatus.CANCELLED, BookingStatus.NO_SHOW}
    ),
    BookingStatus.CHECKED_IN: frozenset({BookingStatus.IN_SERVICE}),
    BookingStatus.IN_SERVICE: frozenset({BookingStatus.COMPLETED}),
    BookingStatus.COMPLETED: frozenset(),
    BookingStatus.CANCELLED: frozenset(),
    BookingStatus.NO_SHOW: frozenset(),
}


class InvalidBookingTransition(ConflictError):
    """Raised instead of docs/06's bare ValueError.

    A bare ValueError would surface as a 500. This carries a machine-readable
    code and becomes a 409 through `core/error_handlers.py`.
    """

    code = "invalid_booking_transition"

    def __init__(self, current: BookingStatus, attempted: BookingStatus) -> None:
        allowed = sorted(_ALLOWED_TRANSITIONS[current]) or "none (terminal)"
        super().__init__(
            f"Cannot move a booking from '{current}' to '{attempted}'. "
            f"Allowed from '{current}': {allowed}."
        )
        self.current = current
        self.attempted = attempted


class CancellationTooLate(ConflictError):
    code = "cancellation_too_late"

    def __init__(self, hours_required: int) -> None:
        super().__init__(f"Free cancellation closes {hours_required} hours before the appointment.")


@dataclass(frozen=True)
class CancellationPolicy:
    """How late a customer may cancel without penalty.

    Per-tenant in principle; the service supplies it, the entity only applies
    it. `free_cancellation_hours=0` means cancel any time before start.
    """

    free_cancellation_hours: int = 24

    def deadline_for(self, starts_at: datetime) -> datetime:
        return starts_at - timedelta(hours=self.free_cancellation_hours)

    def allows_cancellation_at(self, *, starts_at: datetime, now: datetime) -> bool:
        return now <= self.deadline_for(starts_at)


@dataclass
class Booking:
    """A scheduled appointment. Mutable — transitions change its status."""

    id: UUID
    tenant_id: UUID
    business_id: UUID
    location_id: UUID
    service_id: UUID
    provider_id: UUID
    customer_id: UUID
    slot: TimeRange
    price: Money
    status: BookingStatus = BookingStatus.DRAFT
    #: Immutable after construction (docs/11 section 4). Nothing on this entity
    #: reassigns it, and nothing should — a booking that could change channel
    #: after completion could change what the salon was charged for it.
    source: BookingSource = BookingSource.DIRECT_LINK
    cancellation_reason: str | None = None
    notes: str | None = None
    #: Domain events raised by transitions, drained by the service after save.
    #: The entity records what happened; it does not publish (no I/O in domain).
    pending_events: list[object] = field(default_factory=list, repr=False)

    # --- transitions ------------------------------------------------------

    def _transition_to(self, target: BookingStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise InvalidBookingTransition(self.status, target)
        self.status = target

    def confirm(self) -> None:
        self._transition_to(BookingStatus.CONFIRMED)

    def require_payment(self) -> None:
        self._transition_to(BookingStatus.PENDING_PAYMENT)

    def check_in(self) -> None:
        self._transition_to(BookingStatus.CHECKED_IN)

    def start_service(self) -> None:
        self._transition_to(BookingStatus.IN_SERVICE)

    def complete(self) -> None:
        self._transition_to(BookingStatus.COMPLETED)

    def mark_no_show(self) -> None:
        self._transition_to(BookingStatus.NO_SHOW)

    def cancel(
        self,
        *,
        policy: CancellationPolicy,
        now: datetime,
        reason: str | None = None,
        enforce_policy: bool = True,
    ) -> None:
        """Cancel the booking.

        `enforce_policy=False` is for staff cancelling on the business's behalf
        (the salon closed, the provider is ill) — the customer must not be held
        to a deadline for the business's own cancellation.
        """
        if enforce_policy and not policy.allows_cancellation_at(
            starts_at=self.slot.starts_at, now=now
        ):
            raise CancellationTooLate(policy.free_cancellation_hours)
        self._transition_to(BookingStatus.CANCELLED)
        self.cancellation_reason = reason

    # --- queries ----------------------------------------------------------

    @property
    def occupies_calendar(self) -> bool:
        return self.status in BLOCKING_STATUSES

    def conflicts_with(self, other: "Booking") -> bool:
        """Two bookings collide if the same provider is double-booked.

        Both must still occupy the calendar; a cancelled booking never
        conflicts. Uses the half-open interval in `TimeRange`, so a 10:00-11:00
        and an 11:00-12:00 booking do not collide.
        """
        if self.id == other.id:
            return False
        if not (self.occupies_calendar and other.occupies_calendar):
            return False
        if self.provider_id != other.provider_id:
            return False
        return self.slot.overlaps(other.slot)


def build_slot(*, starts_at: datetime, duration_minutes: int) -> TimeRange:
    """Derives the slot end from the service duration.

    The end time is never accepted from the client — it is computed from the
    service's own duration, so a caller cannot request a 5-minute slot for a
    90-minute treatment.
    """
    if starts_at.tzinfo is None:
        raise ValidationDomainError("Booking start time must be timezone-aware.")
    return TimeRange(starts_at=starts_at, ends_at=starts_at + timedelta(minutes=duration_minutes))


def assert_slot_is_bookable(slot: TimeRange, *, now: datetime) -> None:
    if slot.starts_at <= now:
        raise ValidationDomainError("Cannot book a slot in the past.")


# ==========================================================================
# Availability — the `Schedule` and `AvailabilitySlot` aggregates (docs/03
# section 3, docs/06 section 2, README module table).
#
# Everything below is pure: it takes working hours, exceptions, and the times
# already taken, and returns the times that remain. No database, no clock of
# its own — `now` is always passed in, which is what makes it testable and,
# more importantly, *deterministic*: the same inputs always produce the same
# slots in the same order (docs/09 #4).
# ==========================================================================


MINUTES_PER_DAY = 24 * 60


class ScheduleError(ValidationDomainError):
    code = "invalid_schedule"


@dataclass(frozen=True, order=True)
class WorkingWindow:
    """One continuous stretch a provider works, in local wall-clock minutes.

    Stored as minutes from midnight rather than a `time`, because arithmetic on
    wall-clock times across a DST boundary is a trap and minutes-from-midnight
    keeps the intent ("09:00 local, whatever that means today") explicit.

    A split shift — 09:00-13:00 and 16:00-21:00, which is how most GCC salons
    actually run — is two windows on the same weekday, not one with a hole.
    """

    weekday: int  # Monday = 0, matching datetime.weekday()
    start_minute: int
    end_minute: int

    def __post_init__(self) -> None:
        if not 0 <= self.weekday <= 6:
            raise ScheduleError("Weekday must be 0 (Monday) through 6 (Sunday).")
        if not 0 <= self.start_minute < MINUTES_PER_DAY:
            raise ScheduleError("Window start must fall within the day.")
        if not 0 < self.end_minute <= MINUTES_PER_DAY:
            raise ScheduleError("Window end must fall within the day.")
        if self.end_minute <= self.start_minute:
            raise ScheduleError("A working window must end after it starts.")

    @property
    def duration_minutes(self) -> int:
        return self.end_minute - self.start_minute

    def overlaps(self, other: "WorkingWindow") -> bool:
        if self.weekday != other.weekday:
            return False
        return self.start_minute < other.end_minute and other.start_minute < self.end_minute


@dataclass(frozen=True)
class ScheduleException:
    """A named day that overrides the weekly pattern.

    Eid, a public holiday, or one stylist's afternoon off. `windows` empty means
    closed all day; otherwise it replaces the weekly windows entirely rather
    than merging with them — merging makes "closed 14:00-16:00" impossible to
    express.
    """

    on_date: date
    windows: tuple[WorkingWindow, ...] = ()
    reason: str | None = None

    @property
    def is_closed(self) -> bool:
        return not self.windows


@dataclass(frozen=True)
class AvailabilitySlot:
    """A bookable interval. `slot_id` is signed so it cannot be invented."""

    starts_at: datetime
    ends_at: datetime
    provider_id: UUID
    service_id: UUID
    location_id: UUID
    slot_id: str = ""

    @property
    def slot(self) -> TimeRange:
        return TimeRange(starts_at=self.starts_at, ends_at=self.ends_at)


def validate_windows(windows: list[WorkingWindow]) -> list[WorkingWindow]:
    """Rejects a schedule that overlaps itself.

    Two overlapping windows on one weekday would generate the same slot twice,
    and 'deterministic availability' would immediately stop being true.
    """
    ordered = sorted(windows)
    for earlier, later in pairwise(ordered):
        if earlier.overlaps(later):
            raise ScheduleError(
                f"Working windows overlap on weekday {earlier.weekday}: "
                f"{earlier.start_minute}-{earlier.end_minute} and "
                f"{later.start_minute}-{later.end_minute}."
            )
    return ordered


def _local_datetime(day: date, minutes: int, tz: ZoneInfo) -> datetime:
    """Wall-clock minutes on a local date, as an aware UTC instant.

    `minutes` may be 1440 (midnight at the end of the day), which `time()`
    cannot represent — hence the explicit day rollover.
    """
    extra_days, minute_of_day = divmod(minutes, MINUTES_PER_DAY)
    naive = datetime.combine(
        day + timedelta(days=extra_days),
        time(hour=minute_of_day // 60, minute=minute_of_day % 60),
    )
    return naive.replace(tzinfo=tz).astimezone(UTC)


def windows_for_date(
    day: date,
    *,
    weekly: list[WorkingWindow],
    exceptions: dict[date, ScheduleException],
) -> list[WorkingWindow]:
    """The windows that actually apply on one date."""
    override = exceptions.get(day)
    if override is not None:
        return sorted(override.windows)
    return sorted(w for w in weekly if w.weekday == day.weekday())


def generate_availability(
    *,
    weekly: list[WorkingWindow],
    exceptions: dict[date, ScheduleException],
    taken: list[TimeRange],
    provider_id: UUID,
    service_id: UUID,
    location_id: UUID,
    timezone: str,
    date_from: datetime,
    date_to: datetime,
    duration_minutes: int,
    granularity_minutes: int = 15,
    now: datetime,
    lead_time_minutes: int = 0,
) -> list[AvailabilitySlot]:
    """Every slot a provider can still take, in chronological order.

    `taken` is every interval already spoken for — confirmed bookings *and*
    live holds. Both block equally: a slot someone is mid-checkout on must not
    be offered to a second customer.

    Slots are generated on a fixed grid anchored to each window's own start, so
    a 09:00-17:00 window at 15-minute granularity always yields 09:00, 09:15,
    09:30… Anchoring to midnight instead would silently shift every slot when a
    salon changes its opening time.

    A slot must fit entirely inside its window: a 90-minute treatment is not
    offered at 16:00 when the salon closes at 17:00.
    """
    if duration_minutes <= 0:
        raise ScheduleError("Service duration must be positive.")
    if granularity_minutes <= 0:
        raise ScheduleError("Slot granularity must be positive.")
    if date_to <= date_from:
        raise ScheduleError("date_to must be after date_from.")

    tz = ZoneInfo(timezone)
    weekly = validate_windows(weekly)
    duration = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=granularity_minutes)
    earliest = max(date_from, now + timedelta(minutes=lead_time_minutes))

    # Walk local dates, not UTC ones: "Tuesday" is a local concept, and a UTC
    # day boundary falls at 03:00 in Riyadh.
    first_day = date_from.astimezone(tz).date()
    last_day = date_to.astimezone(tz).date()

    slots: list[AvailabilitySlot] = []
    day = first_day
    while day <= last_day:
        for window in windows_for_date(day, weekly=weekly, exceptions=exceptions):
            window_start = _local_datetime(day, window.start_minute, tz)
            window_end = _local_datetime(day, window.end_minute, tz)

            cursor = window_start
            while cursor + duration <= window_end:
                slot_end = cursor + duration
                if cursor >= earliest and slot_end <= date_to:
                    candidate = TimeRange(starts_at=cursor, ends_at=slot_end)
                    if not any(candidate.overlaps(t) for t in taken):
                        slots.append(
                            AvailabilitySlot(
                                starts_at=cursor,
                                ends_at=slot_end,
                                provider_id=provider_id,
                                service_id=service_id,
                                location_id=location_id,
                            )
                        )
                cursor += step
        day += timedelta(days=1)

    slots.sort(key=lambda s: s.starts_at)
    return slots


# --- Signed slot identifiers ---------------------------------------------
#
# docs/07 section 5: "`slot_id` should be a signed or deterministic identifier"
# and "AI agents may query availability but must not invent slots."
#
# The signature is what enforces the second rule. A slot id is derived from the
# tuple that defines the slot, so it is both deterministic (the same slot always
# gets the same id, making it safe to compare and cache) and unforgeable without
# the server secret. It carries no PII — only ids and a timestamp.


def _slot_payload(
    *, tenant_id: UUID, provider_id: UUID, service_id: UUID, starts_at: datetime
) -> str:
    return "|".join(
        [
            str(tenant_id),
            str(provider_id),
            str(service_id),
            starts_at.astimezone(UTC).isoformat(timespec="seconds"),
        ]
    )


def sign_slot_id(
    *,
    tenant_id: UUID,
    provider_id: UUID,
    service_id: UUID,
    starts_at: datetime,
    secret: str,
) -> str:
    """A deterministic, tamper-evident identifier for one bookable slot."""
    payload = _slot_payload(
        tenant_id=tenant_id,
        provider_id=provider_id,
        service_id=service_id,
        starts_at=starts_at,
    )
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return digest[:32]


def verify_slot_id(
    slot_id: str,
    *,
    tenant_id: UUID,
    provider_id: UUID,
    service_id: UUID,
    starts_at: datetime,
    secret: str,
) -> bool:
    expected = sign_slot_id(
        tenant_id=tenant_id,
        provider_id=provider_id,
        service_id=service_id,
        starts_at=starts_at,
        secret=secret,
    )
    # Constant-time: a timing oracle here would let an agent brute-force a slot
    # id byte by byte.
    return hmac.compare_digest(slot_id, expected)


# ==========================================================================
# Fact projections for analytics (docs/13 section 6.2, ADR-0011).
#
# What booking hands the analytics context: the columns a report needs and
# nothing else. No notes, no cancellation reason, and nothing about a customer
# beyond an opaque id — enough to count distinct and returning customers, never
# enough to identify one.
# ==========================================================================


@dataclass(frozen=True)
class BookingFact:
    id: UUID
    location_id: UUID
    service_id: UUID
    provider_id: UUID
    customer_id: UUID
    starts_at: datetime
    ends_at: datetime
    created_at: datetime
    status: BookingStatus
    source: BookingSource
    #: Integer fils, so a sum is exact.
    price_minor: int
    currency: str


@dataclass(frozen=True)
class CustomerVisitFact:
    """One customer's whole history with one business, aggregated."""

    customer_id: UUID
    first_completed_at: datetime | None
    last_completed_at: datetime | None
    completed_count: int
    has_upcoming: bool


@dataclass(frozen=True)
class ProviderCapacityFact:
    """A provider's weekly hours and the dated exceptions inside a range."""

    provider_id: UUID
    weekly: tuple[WorkingWindow, ...]
    exceptions: tuple[ScheduleException, ...]
