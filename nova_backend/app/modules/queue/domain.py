"""queue · DOMAIN layer — the rules.

Layer rule: stdlib, pydantic, and `app.core` values/exceptions only.
Must not import fastapi or sqlalchemy.

Two rich entities, because both have lifecycles that can be corrupted:
a `QueueEntry` that reached COMPLETED without ever being CALLED is a broken
aggregate, not merely bad input, and a `Ticket` that can be redeemed twice is a
free haircut.

Queue entry state machine (docs/06 section 5):

    WAITING ──▶ CALLED ──▶ CHECKED_IN ──▶ IN_SERVICE ──▶ COMPLETED
       │           │
       │           └──▶ MISSED
       └──▶ CANCELLED

Ticket state machine (docs/06 section 6):

    ACTIVE ──▶ REDEEMED
       │
       ├──▶ EXPIRED
       └──▶ REVOKED
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from app.core.exceptions import ConflictError, NotFoundError, ValidationDomainError


class QueueEntryStatus(StrEnum):
    WAITING = "waiting"
    CALLED = "called"
    CHECKED_IN = "checked_in"
    MISSED = "missed"
    IN_SERVICE = "in_service"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TicketStatus(StrEnum):
    ACTIVE = "active"
    REDEEMED = "redeemed"
    EXPIRED = "expired"
    REVOKED = "revoked"


class QueueEntrySource(StrEnum):
    """Where the person in the queue came from.

    docs/03 section 4: walk-ins and appointments share one provider timeline
    but carry different priority weights, so the distinction has to survive
    into the queue rather than being flattened on the way in.
    """

    WALK_IN = "walk_in"
    APPOINTMENT = "appointment"


#: Statuses in which an entry still occupies a place in the line. A missed,
#: cancelled, or completed entry is out of it.
ACTIVE_QUEUE_STATUSES: frozenset[QueueEntryStatus] = frozenset(
    {
        QueueEntryStatus.WAITING,
        QueueEntryStatus.CALLED,
        QueueEntryStatus.CHECKED_IN,
        QueueEntryStatus.IN_SERVICE,
    }
)

_ALLOWED_ENTRY_TRANSITIONS: dict[QueueEntryStatus, frozenset[QueueEntryStatus]] = {
    QueueEntryStatus.WAITING: frozenset({QueueEntryStatus.CALLED, QueueEntryStatus.CANCELLED}),
    # A called customer who does not appear is MISSED, not cancelled — the
    # difference matters for no-show statistics and for the retention agent.
    QueueEntryStatus.CALLED: frozenset(
        {QueueEntryStatus.CHECKED_IN, QueueEntryStatus.MISSED, QueueEntryStatus.CANCELLED}
    ),
    QueueEntryStatus.CHECKED_IN: frozenset({QueueEntryStatus.IN_SERVICE}),
    QueueEntryStatus.IN_SERVICE: frozenset({QueueEntryStatus.COMPLETED}),
    # A missed customer can be put back in line rather than told to start over.
    QueueEntryStatus.MISSED: frozenset({QueueEntryStatus.WAITING}),
    QueueEntryStatus.COMPLETED: frozenset(),
    QueueEntryStatus.CANCELLED: frozenset(),
}

_ALLOWED_TICKET_TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]] = {
    TicketStatus.ACTIVE: frozenset(
        {TicketStatus.REDEEMED, TicketStatus.EXPIRED, TicketStatus.REVOKED}
    ),
    # Terminal. A redeemed ticket is spent; revoking it afterwards would be a
    # way to retroactively deny that someone was served.
    TicketStatus.REDEEMED: frozenset(),
    TicketStatus.EXPIRED: frozenset({TicketStatus.REVOKED}),
    TicketStatus.REVOKED: frozenset(),
}


class InvalidQueueTransition(ConflictError):
    code = "invalid_queue_transition"

    def __init__(self, current: QueueEntryStatus, attempted: QueueEntryStatus) -> None:
        allowed = sorted(_ALLOWED_ENTRY_TRANSITIONS[current]) or "none (terminal)"
        super().__init__(
            f"Cannot move a queue entry from '{current}' to '{attempted}'. "
            f"Allowed from '{current}': {allowed}."
        )


class InvalidTicketTransition(ConflictError):
    code = "invalid_ticket_transition"

    def __init__(self, current: TicketStatus, attempted: TicketStatus) -> None:
        super().__init__(f"Cannot move a ticket from '{current}' to '{attempted}'.")


class QueueClosedError(ConflictError):
    """docs/06 section 9 names this exception explicitly."""

    code = "queue_closed"

    def __init__(self) -> None:
        super().__init__("This queue is closed and is not accepting new entries.")


class TicketInvalidError(ValidationDomainError):
    """docs/06 section 9. Deliberately vague to the client.

    A scanner that reports "wrong signature" versus "expired" versus "unknown
    ticket" tells someone probing with forged QR codes exactly which part to
    fix next.
    """

    code = "ticket_invalid"

    def __init__(self, message: str = "This ticket is not valid.") -> None:
        super().__init__(message)


class TicketExpiredError(ConflictError):
    code = "ticket_expired"

    def __init__(self) -> None:
        super().__init__("This ticket has expired.")


class TicketNotFoundError(NotFoundError):
    code = "ticket_not_found"

    def __init__(self, ticket_id: object) -> None:
        super().__init__(f"Ticket '{ticket_id}' was not found.")


@dataclass
class QueueEntry:
    """One customer's place in the line."""

    id: UUID
    tenant_id: UUID
    queue_id: UUID
    location_id: UUID
    customer_id: UUID
    service_id: UUID
    provider_id: UUID | None
    status: QueueEntryStatus
    position: int
    source: QueueEntrySource = QueueEntrySource.WALK_IN
    party_size: int = 1
    booking_id: UUID | None = None
    joined_at: datetime | None = None
    #: The appointment time, for entries that came from a booking.
    scheduled_for: datetime | None = None
    called_at: datetime | None = None
    checked_in_at: datetime | None = None
    completed_at: datetime | None = None
    pending_events: list[object] = field(default_factory=list, repr=False)

    def _transition_to(self, target: QueueEntryStatus) -> None:
        if target not in _ALLOWED_ENTRY_TRANSITIONS[self.status]:
            raise InvalidQueueTransition(self.status, target)
        self.status = target

    def call(self, *, now: datetime) -> None:
        self._transition_to(QueueEntryStatus.CALLED)
        self.called_at = now

    def check_in(self, *, now: datetime) -> None:
        self._transition_to(QueueEntryStatus.CHECKED_IN)
        self.checked_in_at = now

    def miss(self) -> None:
        self._transition_to(QueueEntryStatus.MISSED)

    def requeue(self) -> None:
        """Puts a missed customer back in line.

        Position is reassigned by the service, not here — the entity does not
        know what else is in the queue.
        """
        self._transition_to(QueueEntryStatus.WAITING)
        self.called_at = None

    def start_service(self) -> None:
        self._transition_to(QueueEntryStatus.IN_SERVICE)

    def complete(self, *, now: datetime) -> None:
        self._transition_to(QueueEntryStatus.COMPLETED)
        self.completed_at = now

    def cancel(self) -> None:
        self._transition_to(QueueEntryStatus.CANCELLED)

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_QUEUE_STATUSES

    @property
    def is_walk_in(self) -> bool:
        return self.source is QueueEntrySource.WALK_IN


def priority_key(entry: QueueEntry, *, walk_in_penalty_minutes: int = 15) -> tuple[float, int, str]:
    """Where an entry sits on the shared provider timeline.

    docs/03 section 4 requires walk-ins and appointments to share one timeline
    with different weights, and docs/08 section 12 requires the ordering to be
    deterministic. Both are satisfied by mapping every entry onto a single
    instant and sorting by it:

      - an appointment sorts at its booked time. It does not jump the queue at
        09:00 merely because it is booked for 17:00.
      - a walk-in sorts at its arrival time plus a penalty, which is what makes
        a booked customer who arrives at the same moment go first. Absent the
        penalty a walk-in standing at the desk would always beat the customer
        who booked ahead, and booking would stop meaning anything.

    Ties break on source (appointments first) and then on the entry id, so the
    order is total and stable — never dependent on the order rows came back
    from the database.
    """
    anchor = entry.scheduled_for or entry.joined_at
    if anchor is None:
        # Nothing to anchor to: sort last rather than crash the whole queue.
        return (float("inf"), 1, str(entry.id))

    timestamp = anchor.timestamp()
    if entry.is_walk_in:
        timestamp += walk_in_penalty_minutes * 60

    return (timestamp, 1 if entry.is_walk_in else 0, str(entry.id))


def order_queue(
    entries: list[QueueEntry], *, walk_in_penalty_minutes: int = 15
) -> list[QueueEntry]:
    """The line, in the order people will actually be seen."""
    return sorted(
        entries,
        key=lambda e: priority_key(e, walk_in_penalty_minutes=walk_in_penalty_minutes),
    )


def estimate_wait_minutes(
    ordered: list[QueueEntry],
    entry_id: UUID,
    *,
    average_service_minutes: int,
    active_providers: int = 1,
) -> int | None:
    """Rough minutes until this entry is called.

    Deliberately crude — people ahead, times the average service length,
    divided by how many chairs are working. A precise estimate would need
    per-service durations and live progress, and would still be wrong the
    moment someone runs long; an honest approximation the customer can see is
    worth more than a precise-looking number that lies.
    """
    providers = max(1, active_providers)
    for index, entry in enumerate(ordered):
        if entry.id == entry_id:
            return int(index * average_service_minutes / providers)
    return None


def next_position(existing_positions: list[int]) -> int:
    """Monotonic, never reused — positions are an audit trail, not an index."""
    return (max(existing_positions) + 1) if existing_positions else 1


# --- Virtual tickets ------------------------------------------------------


@dataclass
class Ticket:
    """A secure virtual ticket. Carries no PII, by construction.

    docs/06 section 6 and docs/07 section 7: the QR payload is a ticket id plus
    a secret, and the database stores only a *hash* of that secret (docs/08
    section 13). A dump of the tickets table therefore does not let anyone
    check in as somebody else.
    """

    id: UUID
    tenant_id: UUID
    ticket_code: str
    qr_token_hash: str
    status: TicketStatus
    expires_at: datetime
    booking_id: UUID | None = None
    queue_entry_id: UUID | None = None
    redeemed_at: datetime | None = None
    revoked_at: datetime | None = None

    def _transition_to(self, target: TicketStatus) -> None:
        if target not in _ALLOWED_TICKET_TRANSITIONS[self.status]:
            raise InvalidTicketTransition(self.status, target)
        self.status = target

    def redeem(self, *, now: datetime) -> None:
        if self.is_expired(now=now):
            raise TicketExpiredError()
        self._transition_to(TicketStatus.REDEEMED)
        self.redeemed_at = now

    def revoke(self, *, now: datetime) -> None:
        self._transition_to(TicketStatus.REVOKED)
        self.revoked_at = now

    def expire(self) -> None:
        self._transition_to(TicketStatus.EXPIRED)

    def is_expired(self, *, now: datetime) -> bool:
        return now >= self.expires_at

    def is_redeemable(self, *, now: datetime) -> bool:
        return self.status is TicketStatus.ACTIVE and not self.is_expired(now=now)


#: Human-readable, shouted across a salon floor. Excludes characters that are
#: ambiguous out loud or on a screen (0/O, 1/I/L), so "NOVA-B8K2" is never
#: misheard as "NOVA-BAK2".
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_ticket_code(*, length: int = 6) -> str:
    suffix = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))
    return f"NV-{suffix}"


def generate_qr_token() -> str:
    """The secret embedded in the QR image. Never stored in the clear."""
    return secrets.token_urlsafe(32)


def hash_qr_token(token: str) -> str:
    """SHA-256, not a password hash: this is a 256-bit random value, not a
    human-chosen secret, so there is nothing for bcrypt's work factor to defend
    against and a slow hash on every reception scan would be pure cost."""
    return hashlib.sha256(token.encode()).hexdigest()


def build_qr_payload(*, ticket_id: UUID, qr_token: str, secret: str) -> str:
    """What the QR image actually encodes.

    Format: `<ticket_id>.<token>.<signature>` — three ids and a MAC, and
    deliberately nothing else. docs/06 section 6 forbids PII here: a printed
    ticket left on a table must not reveal whose it is or what they booked.

    The signature lets a scanner reject a garbage or hand-crafted code without
    a database round trip; the token hash is what actually authenticates it.
    """
    body = f"{ticket_id}.{qr_token}"
    signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{signature}"


def parse_qr_payload(payload: str, *, secret: str) -> tuple[UUID, str]:
    """Verifies the MAC and returns `(ticket_id, qr_token)`.

    Raises `TicketInvalidError` for anything malformed or unsigned — with a
    single generic message, so this cannot be used as an oracle.
    """
    parts = payload.strip().split(".")
    if len(parts) != 3:
        raise TicketInvalidError()

    ticket_id_raw, qr_token, signature = parts
    body = f"{ticket_id_raw}.{qr_token}"
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]

    # Constant-time: a timing leak here would let someone forge a signature
    # character by character.
    if not hmac.compare_digest(signature, expected):
        raise TicketInvalidError()

    try:
        ticket_id = UUID(ticket_id_raw)
    except ValueError as exc:
        raise TicketInvalidError() from exc

    return ticket_id, qr_token


def verify_qr_token(presented_token: str, *, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_qr_token(presented_token), stored_hash)


def default_ticket_expiry(*, now: datetime, ttl_hours: int) -> datetime:
    """A ticket is a bearer credential; an unbounded one is a standing key."""
    return now + timedelta(hours=ttl_hours)


@dataclass(frozen=True)
class QueueEntryFact:
    """A queue entry as the analytics context sees it (docs/13 section 6.2).

    No customer id at all: queue reports count walk-ins and time their waits,
    and neither needs to know who waited.
    """

    location_id: UUID
    service_id: UUID
    provider_id: UUID | None
    source: QueueEntrySource
    status: QueueEntryStatus
    party_size: int
    joined_at: datetime
    called_at: datetime | None
    completed_at: datetime | None
