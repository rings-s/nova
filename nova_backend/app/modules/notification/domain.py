"""notification · DOMAIN layer — the rules.

Layer rule: stdlib, pydantic, and `app.core` values/exceptions only.
Must not import fastapi, sqlalchemy, or an HTTP client.

Mostly pure functions over a small status enum. The interesting rules here are
not about lifecycle — they are about *permission to speak to someone*:

  - consent is per-channel and defaults to withheld (PDPL),
  - marketing obeys quiet hours; a booking confirmation does not,
  - outbound messages are pre-approved templates, never free text.

Notification status:

    PENDING ──▶ SENT ──▶ DELIVERED ──▶ READ
       │          │
       │          └──▶ FAILED
       ├──▶ SUPPRESSED   (consent withheld, or quiet hours for marketing)
       └──▶ FAILED
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.core.exceptions import ConflictError, ValidationDomainError


class NotificationChannel(StrEnum):
    WHATSAPP = "whatsapp"
    SMS = "sms"
    EMAIL = "email"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    #: Never sent, on purpose. Distinct from FAILED: nothing went wrong, we
    #: were simply not permitted to send. Collapsing the two would hide a
    #: consent problem inside a delivery-error metric.
    SUPPRESSED = "suppressed"


class NotificationCategory(StrEnum):
    """What a message is *for*, which decides the rules that apply to it.

    TRANSACTIONAL is something the customer asked for by acting — a booking
    confirmation, a "you're next" call. It ignores quiet hours, because a 6am
    appointment reminder at 10pm the night before is the entire point.

    MARKETING is something the business wants. It requires explicit marketing
    consent and obeys quiet hours.
    """

    TRANSACTIONAL = "transactional"
    MARKETING = "marketing"


#: Pre-approved WhatsApp template names. Free text is not sendable outside a
#: 24-hour session window, and an allowlist here means a typo in a template
#: name fails locally instead of at the BSP.
class MessageTemplate(StrEnum):
    BOOKING_CONFIRMED = "booking_confirmed"
    BOOKING_CANCELLED = "booking_cancelled"
    BOOKING_RESCHEDULED = "booking_rescheduled"
    BOOKING_REMINDER = "booking_reminder"
    QUEUE_JOINED = "queue_joined"
    QUEUE_CALLED = "queue_called"
    TICKET_ISSUED = "ticket_issued"
    PAYMENT_RECEIPT = "payment_receipt"
    WIN_BACK = "win_back"


_TEMPLATE_CATEGORY: dict[MessageTemplate, NotificationCategory] = {
    MessageTemplate.BOOKING_CONFIRMED: NotificationCategory.TRANSACTIONAL,
    MessageTemplate.BOOKING_CANCELLED: NotificationCategory.TRANSACTIONAL,
    MessageTemplate.BOOKING_RESCHEDULED: NotificationCategory.TRANSACTIONAL,
    MessageTemplate.BOOKING_REMINDER: NotificationCategory.TRANSACTIONAL,
    MessageTemplate.QUEUE_JOINED: NotificationCategory.TRANSACTIONAL,
    MessageTemplate.QUEUE_CALLED: NotificationCategory.TRANSACTIONAL,
    MessageTemplate.TICKET_ISSUED: NotificationCategory.TRANSACTIONAL,
    MessageTemplate.PAYMENT_RECEIPT: NotificationCategory.TRANSACTIONAL,
    MessageTemplate.WIN_BACK: NotificationCategory.MARKETING,
}

_ALLOWED_TRANSITIONS: dict[NotificationStatus, frozenset[NotificationStatus]] = {
    NotificationStatus.PENDING: frozenset(
        {
            NotificationStatus.SENT,
            NotificationStatus.FAILED,
            NotificationStatus.SUPPRESSED,
        }
    ),
    NotificationStatus.SENT: frozenset({NotificationStatus.DELIVERED, NotificationStatus.FAILED}),
    NotificationStatus.DELIVERED: frozenset({NotificationStatus.READ}),
    NotificationStatus.READ: frozenset(),
    NotificationStatus.FAILED: frozenset(),
    NotificationStatus.SUPPRESSED: frozenset(),
}


class InvalidNotificationTransition(ConflictError):
    code = "invalid_notification_transition"

    def __init__(self, current: NotificationStatus, attempted: NotificationStatus) -> None:
        super().__init__(f"Cannot move a notification from '{current}' to '{attempted}'.")


class ConsentWithheldError(ConflictError):
    """PDPL: no consent, no message. Not a failure — a refusal."""

    code = "consent_withheld"

    def __init__(self, channel: NotificationChannel) -> None:
        super().__init__(f"This customer has not consented to {channel} messages.")


def category_for(template: MessageTemplate) -> NotificationCategory:
    return _TEMPLATE_CATEGORY[template]


def has_consent(
    *,
    channel: NotificationChannel,
    category: NotificationCategory,
    whatsapp_consent: bool,
    marketing_consent: bool,
) -> bool:
    """Whether we may send this at all.

    Marketing needs marketing consent *in addition to* channel consent —
    agreeing to receive a booking confirmation on WhatsApp is not agreeing to
    receive offers there.
    """
    if category is NotificationCategory.MARKETING and not marketing_consent:
        return False
    if channel is NotificationChannel.WHATSAPP:
        return whatsapp_consent
    return True


def is_within_quiet_hours(at: datetime, *, timezone: str, start_hour: int, end_hour: int) -> bool:
    """Whether a local time falls inside the do-not-disturb window.

    Evaluated in the *customer's* local timezone, not the server's — a Riyadh
    salon messaging at 22:00 UTC is messaging at 01:00 local, which is exactly
    what this prevents. The window normally wraps midnight (22:00-08:00), so
    the comparison differs depending on whether it does.
    """
    local_hour = at.astimezone(ZoneInfo(timezone)).hour
    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= local_hour < end_hour
    return local_hour >= start_hour or local_hour < end_hour


def next_send_time(at: datetime, *, timezone: str, end_hour: int) -> datetime:
    """When a quiet-hours-suppressed message may go out instead.

    Held until the window opens rather than dropped: a win-back offer is still
    worth sending at 08:00, just not at 02:00.

    The result is computed in local time and converted back, so it lands at
    08:00 *for the customer* rather than 08:00 somewhere else.
    """
    tz = ZoneInfo(timezone)
    local = at.astimezone(tz)
    target = local.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if target <= local:
        # Already past this morning's opening: the next one is tomorrow.
        # Adding a day to the local datetime (not the UTC one) keeps it correct
        # across a DST change.
        target = (local + timedelta(days=1)).replace(
            hour=end_hour, minute=0, second=0, microsecond=0
        )
    return target.astimezone(at.tzinfo or tz)


#: How long to wait before re-attempting a failed send, indexed by the number
#: of sends already made. A BSP returning 500 for thirty seconds must not cost
#: the customer their booking confirmation, which is exactly what a single
#: terminal attempt did.
#:
#: Deliberately shorter and shallower than the outbox ladder in
#: `app/db/outbox.py`: an outbox event is still worth delivering two hours
#: late, whereas "you're next in the queue" is worth nothing by then. The last
#: retry therefore lands within about half an hour rather than a working day.
DELIVERY_BACKOFF_SECONDS: tuple[int, ...] = (30, 300, 1800)

#: The initial send plus one attempt per backoff step.
MAX_DELIVERY_ATTEMPTS = len(DELIVERY_BACKOFF_SECONDS) + 1


def next_delivery_attempt_at(now: datetime, *, attempts: int) -> datetime | None:
    """When to retry a failed send, or None once the attempts are exhausted.

    `attempts` counts sends already made, so the first failure passes 1 and
    waits 30 seconds. Returning None is what makes FAILED terminal: the caller
    stops rescheduling and the row is no longer picked up for delivery.
    """
    if attempts < 1 or attempts > len(DELIVERY_BACKOFF_SECONDS):
        return None
    return now + timedelta(seconds=DELIVERY_BACKOFF_SECONDS[attempts - 1])


@dataclass
class Notification:
    """One outbound message and what happened to it."""

    id: object
    tenant_id: object
    customer_id: object
    channel: NotificationChannel
    template: MessageTemplate
    status: NotificationStatus
    payload: dict[str, str]
    provider_message_id: str | None = None
    error: str | None = None
    sent_at: datetime | None = None
    scheduled_for: datetime | None = None

    def _transition_to(self, target: NotificationStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise InvalidNotificationTransition(self.status, target)
        self.status = target

    def mark_sent(self, *, provider_message_id: str, now: datetime) -> None:
        self._transition_to(NotificationStatus.SENT)
        self.provider_message_id = provider_message_id
        self.sent_at = now

    def mark_delivered(self) -> None:
        self._transition_to(NotificationStatus.DELIVERED)

    def mark_read(self) -> None:
        self._transition_to(NotificationStatus.READ)

    def mark_failed(self, *, error: str) -> None:
        self._transition_to(NotificationStatus.FAILED)
        self.error = error[:1000]

    def suppress(self, *, reason: str) -> None:
        self._transition_to(NotificationStatus.SUPPRESSED)
        self.error = reason


def render_template_params(template: MessageTemplate, context: dict[str, str]) -> dict[str, str]:
    """The variables a template needs, and nothing else.

    An allowlist per template rather than passing the whole context: a context
    dict assembled from a booking carries names and phone numbers, and sending
    the lot to a third-party BSP because a template happened to accept extra
    parameters is a quiet data leak.
    """
    required = _TEMPLATE_PARAMS.get(template, ())
    missing = [key for key in required if key not in context]
    if missing:
        raise ValidationDomainError(
            f"Template '{template}' is missing parameters: {', '.join(missing)}."
        )
    return {key: str(context[key]) for key in required}


_TEMPLATE_PARAMS: dict[MessageTemplate, tuple[str, ...]] = {
    MessageTemplate.BOOKING_CONFIRMED: ("customer_name", "service_name", "starts_at"),
    MessageTemplate.BOOKING_CANCELLED: ("customer_name", "starts_at"),
    MessageTemplate.BOOKING_RESCHEDULED: ("customer_name", "previous_starts_at", "starts_at"),
    MessageTemplate.BOOKING_REMINDER: ("customer_name", "service_name", "starts_at"),
    MessageTemplate.QUEUE_JOINED: ("customer_name", "position"),
    MessageTemplate.QUEUE_CALLED: ("customer_name",),
    MessageTemplate.TICKET_ISSUED: ("customer_name", "ticket_code", "ticket_url"),
    MessageTemplate.PAYMENT_RECEIPT: ("customer_name", "amount", "currency"),
    MessageTemplate.WIN_BACK: ("customer_name", "business_name"),
}
