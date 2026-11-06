"""queue · APPLICATION layer — use cases.

Layer rule: domain, repository, events, and other modules' *services*.
Must not import fastapi. Must not import another module's models or repository.

Services flush, never commit. The router owns the transaction boundary.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.events import publish_event
from app.core.exceptions import ValidationDomainError
from app.core.security import Principal
from app.core.values import TimeRange
from app.modules.booking.service import BookingService
from app.modules.catalog.service import CatalogService
from app.modules.identity.service import CustomerService
from app.modules.queue.domain import (
    QueueClosedError,
    QueueEntry,
    QueueEntryFact,
    QueueEntrySource,
    QueueEntryStatus,
    Ticket,
    TicketExpiredError,
    TicketInvalidError,
    TicketStatus,
    build_qr_payload,
    default_ticket_expiry,
    estimate_wait_minutes,
    generate_qr_token,
    generate_ticket_code,
    hash_qr_token,
    next_position,
    order_queue,
    parse_qr_payload,
    places_in_line,
    verify_qr_token,
)
from app.modules.queue.events import (
    CustomerCalled,
    CustomerCheckedIn,
    QueueEntryJoined,
    QueueEntryMissed,
    TicketIssued,
)
from app.modules.queue.exceptions import (
    AlreadyInQueueError,
    NoOneWaitingError,
    QueueEntryNotFoundError,
    QueueNotFoundError,
)
from app.modules.queue.models import QueueRecord
from app.modules.queue.repository import (
    QueueEntryRepository,
    QueueRepository,
    TicketRepository,
    UnscopedQueueEntryRepository,
    UnscopedTicketRepository,
)


@dataclass(frozen=True)
class IssuedTicket:
    """A freshly issued ticket plus the one-time payload for its QR image.

    `qr_payload` exists only here, in memory, on the way to the customer. It is
    never stored — only its hash is — so it cannot be recovered later. If the
    customer loses it, reception reissues rather than looks it up.
    """

    ticket: Ticket
    qr_payload: str
    ticket_page_url: str


@dataclass(frozen=True)
class QueuePosition:
    entry: QueueEntry
    #: None unless the entry is still waiting for its turn.
    place_in_line: int | None
    estimated_wait_minutes: int | None


@dataclass(frozen=True)
class JoinedQueue:
    """Where a new entry stands. It has just joined, so it is waiting and has a place."""

    entry: QueueEntry
    place_in_line: int
    estimated_wait_minutes: int | None


class QueueService:
    def __init__(
        self,
        *,
        queues: QueueRepository,
        entries: QueueEntryRepository,
        tickets: TicketRepository,
        catalog: CatalogService,
        customers: CustomerService,
        bookings: BookingService,
        tenant_id: UUID,
        secret_key: str,
        public_app_url: str,
        ticket_ttl_hours: int = 12,
        walk_in_penalty_minutes: int = 15,
    ) -> None:
        self.queues = queues
        self.entries = entries
        self.tickets = tickets
        self.catalog = catalog
        self.customers = customers
        self.bookings = bookings
        self.tenant_id = tenant_id
        self.secret_key = secret_key
        self.public_app_url = public_app_url.rstrip("/")
        self.ticket_ttl_hours = ticket_ttl_hours
        self.walk_in_penalty_minutes = walk_in_penalty_minutes

    @property
    def session(self):
        return self.queues.session

    # --- queues -----------------------------------------------------------

    async def create_queue(
        self,
        *,
        location_id: UUID,
        name_en: str = "Main Queue",
        name_ar: str = "الطابور الرئيسي",
        average_service_minutes: int = 30,
    ) -> QueueRecord:
        await self.catalog.get_location(location_id)
        queue = QueueRecord(
            tenant_id=self.tenant_id,
            location_id=location_id,
            name_en=name_en,
            name_ar=name_ar,
            average_service_minutes=average_service_minutes,
        )
        self.queues.add(queue)
        await self.queues.session.flush()
        return queue

    async def get_queue(self, queue_id: UUID) -> QueueRecord:
        queue = await self.queues.get(queue_id)
        if queue is None:
            raise QueueNotFoundError(queue_id)
        return queue

    async def list_queues(self, location_id: UUID) -> list[QueueRecord]:
        await self.catalog.get_location(location_id)
        return await self.queues.list_for_location(location_id)

    async def list_queue_facts(
        self, *, location_ids: Sequence[UUID], window: TimeRange, limit: int
    ) -> list[QueueEntryFact]:
        """For the analytics context (docs/13 section 6.2)."""
        return await self.entries.list_facts(location_ids=location_ids, window=window, limit=limit)

    async def set_queue_open(self, queue_id: UUID, *, is_open: bool) -> QueueRecord:
        queue = await self.get_queue(queue_id)
        queue.is_open = is_open
        await self.queues.session.flush()
        return queue

    # --- joining ----------------------------------------------------------

    async def join(
        self,
        *,
        queue_id: UUID,
        customer_reference_id: UUID,
        self_service: bool,
        service_id: UUID | None = None,
        provider_id: UUID | None = None,
        party_size: int = 1,
        booking_id: UUID | None = None,
        now: datetime | None = None,
    ) -> JoinedQueue:
        """Adds a walk-in — or an arriving appointment — to the line.

        An appointment (`booking_id`) must be the customer's own, still on the
        calendar, at this queue's branch: it sorts at its booked time, ahead
        of walk-ins, so any booking id would otherwise be a way to jump the
        line. Its service is the booking's when none is given.
        """
        now = now or datetime.now(UTC)

        queue = await self.get_queue(queue_id)
        if not queue.is_open:
            raise QueueClosedError()

        if provider_id is not None:
            await self._provider_at(queue, provider_id)

        customer = await self.customers.resolve_for_booking(
            customer_reference_id, self_service=self_service
        )

        source = QueueEntrySource.WALK_IN
        scheduled_for: datetime | None = None
        if booking_id is not None:
            # An arriving appointment joins the same line rather than a
            # parallel one — docs/03 section 4 requires one shared timeline.
            booking = await self.bookings.get_for_customer(
                booking_id, customer.id, location_id=queue.location_id
            )
            source = QueueEntrySource.APPOINTMENT
            scheduled_for = booking.slot.starts_at
            provider_id = provider_id or booking.provider_id
            service_id = service_id or booking.service_id

        if service_id is None:
            raise ValidationDomainError("A walk-in needs a service_id.")
        await self.catalog.get_service(service_id)

        # Positions are assigned under a lock: two people joining at the same
        # instant would otherwise read the same max and collide on the unique
        # (queue_id, position) constraint.
        await self.queues.lock_queue(queue_id)

        existing = await self.entries.find_active_for_customer(
            queue_id=queue_id, customer_id=customer.id
        )
        if existing is not None:
            raise AlreadyInQueueError()

        position = next_position([await self.entries.max_position(queue_id)])

        entry = await self.entries.add_entry(
            QueueEntry(
                id=uuid4(),
                tenant_id=self.tenant_id,
                queue_id=queue_id,
                location_id=queue.location_id,
                customer_id=customer.id,
                service_id=service_id,
                provider_id=provider_id,
                status=QueueEntryStatus.WAITING,
                position=position,
                source=source,
                party_size=party_size,
                booking_id=booking_id,
                joined_at=now,
                scheduled_for=scheduled_for,
            )
        )

        standing = await self._position_of(queue, entry)
        if standing.place_in_line is None:  # pragma: no cover - a new entry is waiting
            raise QueueEntryNotFoundError(entry.id)
        joined = JoinedQueue(
            entry=entry,
            place_in_line=standing.place_in_line,
            estimated_wait_minutes=standing.estimated_wait_minutes,
        )
        await publish_event(
            self.session,
            QueueEntryJoined(
                tenant_id=self.tenant_id,
                queue_id=queue_id,
                entry_id=entry.id,
                customer_id=customer.id,
                source=str(source),
                place_in_line=joined.place_in_line,
            ),
        )
        return joined

    # --- the line ---------------------------------------------------------

    async def list_queue(self, queue_id: UUID) -> list[QueueEntry]:
        """The line in the order people will actually be seen."""
        await self.get_queue(queue_id)
        entries = await self.entries.list_active(queue_id)
        return order_queue(entries, walk_in_penalty_minutes=self.walk_in_penalty_minutes)

    async def list_board(self, queue_id: UUID) -> list[QueuePosition]:
        """Reception's board: the line in order, then whoever was missed.

        Missed entries are off the line but stay on the board, or nobody could
        reach them to requeue or remove them.
        """
        queue = await self.get_queue(queue_id)
        ordered = await self.list_queue(queue_id)
        missed = await self.entries.list_missed(queue_id)
        places = places_in_line(ordered)
        active_providers = await self._active_providers(queue)
        return [
            QueuePosition(
                entry=entry,
                place_in_line=places.get(entry.id),
                estimated_wait_minutes=estimate_wait_minutes(
                    ordered,
                    entry.id,
                    average_service_minutes=queue.average_service_minutes,
                    active_providers=active_providers,
                ),
            )
            for entry in ordered
        ] + [
            QueuePosition(entry=entry, place_in_line=None, estimated_wait_minutes=None)
            for entry in missed
        ]

    async def customer_names(self, customer_ids: Sequence[UUID]) -> dict[UUID, str]:
        """Who is on the board, for reception. Staff reads only."""
        return await self.customers.names_for(customer_ids)

    async def peek_next(self, queue_id: UUID) -> QueueEntry | None:
        waiting = await self.entries.list_waiting(queue_id)
        ordered = order_queue(waiting, walk_in_penalty_minutes=self.walk_in_penalty_minutes)
        return ordered[0] if ordered else None

    async def call_next(
        self, queue_id: UUID, *, provider_id: UUID | None = None, now: datetime | None = None
    ) -> QueueEntry:
        """Calls whoever the ordering says is next.

        Reception does not choose — the domain does. Letting staff pick out of
        order is exactly how a queue stops being fair, and how "deterministic
        ordering" (docs/08 section 12) becomes untrue in practice.
        """
        now = now or datetime.now(UTC)
        queue = await self.get_queue(queue_id)
        if provider_id is not None:
            await self._provider_at(queue, provider_id)

        await self.queues.lock_queue(queue_id)
        entry = await self.peek_next(queue_id)
        if entry is None:
            raise NoOneWaitingError()

        entry.call(now=now)
        if provider_id is not None:
            entry.provider_id = provider_id
        saved = await self.entries.save_entry(entry)

        await publish_event(
            self.session,
            CustomerCalled(
                tenant_id=self.tenant_id,
                queue_id=queue_id,
                entry_id=saved.id,
                customer_id=saved.customer_id,
                position=saved.position,
            ),
        )
        return saved

    async def get_entry(self, entry_id: UUID) -> QueueEntry:
        entry = await self.entries.get_entry(entry_id)
        if entry is None:
            raise QueueEntryNotFoundError(entry_id)
        return entry

    async def assert_entry_visible_to(self, entry_id: UUID, principal: Principal) -> QueueEntry:
        """A queue entry the caller is entitled to see or act on.

        `GET /queues/{id}/entries` is already staff-only because, in its own
        words, "it names every waiting customer". Reading them one at a time
        through a bare entry id has to be held to the same standard, or the
        list restriction means nothing.

        404 rather than 403, for the same reason as bookings: a 403 confirms
        the entry exists.
        """
        entry = await self.get_entry(entry_id)
        if principal.is_staff:
            return entry

        customer = await self.customers.find_for_user(principal.subject_id)
        if customer is None or customer.id != entry.customer_id:
            raise QueueEntryNotFoundError(entry_id)
        return entry

    async def assert_ticket_subject_visible_to(
        self,
        principal: Principal,
        *,
        booking_id: UUID | None = None,
        queue_entry_id: UUID | None = None,
    ) -> None:
        """Guards ticket issuance against the subject's owner.

        This is the check that stops the worst thing an authenticated stranger
        could otherwise do here. `issue_ticket` **revokes an existing valid
        ticket** and returns a fresh redeemable QR payload, so without an
        ownership check any account could name someone else's booking, destroy
        the QR code that person is standing at the counter holding, and receive
        a working one for their appointment — a denial and a credential theft
        in a single call.
        """
        if principal.is_staff:
            return
        if booking_id is not None:
            await self.bookings.assert_visible_to(booking_id, principal)
        if queue_entry_id is not None:
            await self.assert_entry_visible_to(queue_entry_id, principal)

    async def mark_missed(self, entry_id: UUID) -> QueueEntry:
        entry = await self.get_entry(entry_id)
        entry.miss()
        saved = await self.entries.save_entry(entry)

        await publish_event(
            self.session,
            QueueEntryMissed(
                tenant_id=self.tenant_id,
                queue_id=saved.queue_id,
                entry_id=saved.id,
                customer_id=saved.customer_id,
            ),
        )
        return saved

    async def requeue(self, entry_id: UUID, *, now: datetime | None = None) -> QueueEntry:
        """Puts a missed customer back, at the end rather than where they were."""
        entry = await self.get_entry(entry_id)
        await self.queues.lock_queue(entry.queue_id)
        entry.requeue(now=now or datetime.now(UTC))
        entry.position = next_position([await self.entries.max_position(entry.queue_id)])
        return await self.entries.save_entry(entry)

    async def check_in_entry(self, entry_id: UUID, *, now: datetime | None = None) -> QueueEntry:
        now = now or datetime.now(UTC)
        entry = await self.get_entry(entry_id)
        entry.check_in(now=now)
        saved = await self.entries.save_entry(entry)

        await publish_event(
            self.session,
            CustomerCheckedIn(
                tenant_id=self.tenant_id,
                queue_id=saved.queue_id,
                entry_id=saved.id,
                customer_id=saved.customer_id,
            ),
        )
        return saved

    async def start_service(self, entry_id: UUID) -> QueueEntry:
        entry = await self.get_entry(entry_id)
        entry.start_service()
        return await self.entries.save_entry(entry)

    async def complete(self, entry_id: UUID, *, now: datetime | None = None) -> QueueEntry:
        entry = await self.get_entry(entry_id)
        entry.complete(now=now or datetime.now(UTC))
        return await self.entries.save_entry(entry)

    async def cancel(self, entry_id: UUID) -> QueueEntry:
        entry = await self.get_entry(entry_id)
        entry.cancel()
        return await self.entries.save_entry(entry)

    async def position_of(self, entry_id: UUID) -> QueuePosition:
        entry = await self.get_entry(entry_id)
        queue = await self.get_queue(entry.queue_id)
        return await self._position_of(queue, entry)

    async def _position_of(self, queue: QueueRecord, entry: QueueEntry) -> QueuePosition:
        ordered = await self.list_queue(queue.id)
        return QueuePosition(
            entry=entry,
            place_in_line=places_in_line(ordered).get(entry.id),
            estimated_wait_minutes=estimate_wait_minutes(
                ordered,
                entry.id,
                average_service_minutes=queue.average_service_minutes,
                active_providers=await self._active_providers(queue),
            ),
        )

    async def _active_providers(self, queue: QueueRecord) -> int:
        """Every working chair at the branch shortens the wait, not just one."""
        providers = await self.catalog.list_providers(queue.location_id)
        return sum(1 for p in providers if p.is_active)

    async def _provider_at(self, queue: QueueRecord, provider_id: UUID) -> None:
        """A provider id named for this queue must work at its branch."""
        provider = await self.catalog.get_provider(provider_id)
        if provider.location_id != queue.location_id:
            raise QueueNotFoundError(queue.id)

    # --- tickets ----------------------------------------------------------

    async def issue_ticket(
        self,
        *,
        booking_id: UUID | None = None,
        queue_entry_id: UUID | None = None,
        now: datetime | None = None,
    ) -> IssuedTicket:
        """Issues a virtual ticket for a booking or a queue entry.

        Idempotent by reuse: asking twice for the same subject returns the
        existing active ticket rather than minting a second valid QR code for
        the same appointment. Two working tickets for one booking means two
        people can check in.
        """
        now = now or datetime.now(UTC)

        if booking_id is None and queue_entry_id is None:
            raise TicketInvalidError("A ticket needs a booking or a queue entry.")

        appointment_ends_at: datetime | None = None
        if booking_id is not None:
            booking = await self.bookings.get(booking_id)
            appointment_ends_at = booking.slot.ends_at
            existing = await self.tickets.find_active_for_booking(booking_id)
        else:
            await self.get_entry(queue_entry_id)  # type: ignore[arg-type]
            existing = await self.tickets.find_active_for_queue_entry(queue_entry_id)  # type: ignore[arg-type]

        if existing is not None and existing.is_redeemable(now=now):
            # The token cannot be recovered from the hash, so a reissue request
            # for a still-valid ticket revokes and replaces rather than
            # returning a payload we no longer have.
            existing.revoke(now=now)
            await self.tickets.save_ticket(existing)

        qr_token = generate_qr_token()
        ticket = Ticket(
            id=uuid4(),
            tenant_id=self.tenant_id,
            ticket_code=generate_ticket_code(),
            qr_token_hash=hash_qr_token(qr_token),
            status=TicketStatus.ACTIVE,
            expires_at=default_ticket_expiry(
                now=now, ttl_hours=self.ticket_ttl_hours, appointment_ends_at=appointment_ends_at
            ),
            booking_id=booking_id,
            queue_entry_id=queue_entry_id,
        )
        saved = await self.tickets.add_ticket(ticket)

        await publish_event(
            self.session,
            TicketIssued(
                tenant_id=self.tenant_id,
                ticket_id=saved.id,
                booking_id=booking_id,
                queue_entry_id=queue_entry_id,
            ),
        )

        return IssuedTicket(
            ticket=saved,
            qr_payload=build_qr_payload(
                ticket_id=saved.id, qr_token=qr_token, secret=self.secret_key
            ),
            ticket_page_url=f"{self.public_app_url}/t/{saved.ticket_code}",
        )

    async def ticket_page_for_booking(self, booking_id: UUID) -> str | None:
        """The page of a booking's active ticket, to send the customer; None if it has none."""
        ticket = await self.tickets.find_active_for_booking(booking_id)
        if ticket is None:
            return None
        return f"{self.public_app_url}/t/{ticket.ticket_code}"

    async def redeem_ticket(
        self, *, qr_payload: str, now: datetime | None = None
    ) -> tuple[Ticket, QueueEntry | None]:
        """Reception scans a QR code and checks the customer in.

        Validation order matters, and every failure raises the same generic
        error: signature, then tenant, then status, then expiry (docs/07
        section 7). Returning a different message per step would let someone
        with a forged code work out which part to fix.

        Redemption is idempotent (docs/08 section 13): scanning the same code
        twice — which happens constantly when a scanner double-fires — returns
        the same result instead of erroring at a busy reception desk.
        """
        now = now or datetime.now(UTC)

        ticket_id, qr_token = parse_qr_payload(qr_payload, secret=self.secret_key)

        # Tenant-scoped repository: a ticket from another salon is simply not
        # found here, so a valid code cannot be redeemed at the wrong branch.
        ticket = await self.tickets.get_ticket(ticket_id)
        if ticket is None:
            raise TicketInvalidError()

        if not verify_qr_token(qr_token, stored_hash=ticket.qr_token_hash):
            raise TicketInvalidError()

        if ticket.status is TicketStatus.REDEEMED:
            already_checked_in = (
                await self.entries.get_entry(ticket.queue_entry_id)
                if ticket.queue_entry_id
                else None
            )
            return ticket, already_checked_in

        if ticket.status is not TicketStatus.ACTIVE:
            raise TicketInvalidError()

        if ticket.is_expired(now=now):
            raise TicketExpiredError()

        ticket.redeem(now=now)
        saved_ticket = await self.tickets.save_ticket(ticket)

        # Redeeming is what "reception scanned you in" means, so it drives the
        # subject's own check-in rather than leaving staff to do it twice.
        entry: QueueEntry | None = None
        if ticket.queue_entry_id is not None:
            entry = await self.check_in_entry(ticket.queue_entry_id, now=now)
        elif ticket.booking_id is not None:
            await self.bookings.check_in(ticket.booking_id)
            # An appointment already called from the line is checked in there
            # too, or it would sit at "called" after the customer was scanned.
            queued = await self.entries.find_for_booking(ticket.booking_id)
            if queued is not None and queued.status is QueueEntryStatus.CALLED:
                entry = await self.check_in_entry(queued.id, now=now)

        return saved_ticket, entry

    async def revoke_ticket(self, ticket_id: UUID, *, now: datetime | None = None) -> Ticket:
        ticket = await self.tickets.get_ticket(ticket_id)
        if ticket is None:
            raise TicketInvalidError()
        ticket.revoke(now=now or datetime.now(UTC))
        return await self.tickets.save_ticket(ticket)

    async def expire_stale_tickets(self, *, now: datetime | None = None) -> int:
        """Sweeps active tickets past their expiry. Called by the worker."""
        now = now or datetime.now(UTC)
        stale = await self.tickets.list_expired_active(now=now)
        for ticket in stale:
            ticket.expire()
            await self.tickets.save_ticket(ticket)
        return len(stale)


__all__ = [
    "IssuedTicket",
    "JoinedQueue",
    "QueuePosition",
    "QueueService",
    "QueueSweeper",
    "TicketSweeper",
]


class QueueSweeper:
    """The worker's cross-tenant queue housekeeping."""

    def __init__(self, entries: UnscopedQueueEntryRepository) -> None:
        self.entries = entries

    async def cancel_stale(self, *, joined_before: datetime, limit: int = 500) -> int:
        """Cancels entries that joined before `joined_before` and were never
        served, `limit` at a time until none are left. Returns how many.

        Not cosmetic: the line is ordered by arrival, so yesterday's leftovers
        would otherwise sit at the head of it and be called first the next
        morning.
        """
        total = 0
        while True:
            batch = await self.entries.cancel_stale(joined_before=joined_before, limit=limit)
            total += batch
            if batch < limit:
                return total


class TicketSweeper:
    """The worker's cross-tenant ticket housekeeping."""

    def __init__(self, tickets: UnscopedTicketRepository) -> None:
        self.tickets = tickets

    async def expire_stale(self, *, now: datetime, limit: int = 500) -> int:
        """Moves ACTIVE tickets past their expiry to EXPIRED, `limit` at a time until
        none are left. Returns how many.

        Cosmetic for security (`Ticket.is_redeemable` already refuses an
        expired ticket at scan time), but it keeps reception's screen honest.
        """
        total = 0
        while True:
            batch = await self.tickets.expire_stale(now=now, limit=limit)
            total += batch
            if batch < limit:
                return total
