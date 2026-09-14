"""booking · APPLICATION layer — use cases.

Layer rule: domain, repository, events, and other modules' *services*.
Must not import fastapi. Must not import another module's models or repository.

Services flush, never commit. The router owns the transaction boundary.

The shape of every use case here is the same:
    load -> ask the domain -> persist -> publish
Business rules live in `domain.py`; this file only sequences them.
"""

import secrets
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from app.core.events import publish_event
from app.core.security import Principal
from app.core.values import Money, TimeRange
from app.modules.booking.domain import (
    AvailabilitySlot,
    Booking,
    BookingFact,
    BookingSource,
    BookingStatus,
    CancellationPolicy,
    CustomerVisitFact,
    ProviderCapacityFact,
    ScheduleError,
    WorkingWindow,
    assert_slot_is_bookable,
    build_slot,
    generate_availability,
    sign_slot_id,
    validate_windows,
    verify_slot_id,
)
from app.modules.booking.events import (
    BookingCancelled,
    BookingCompleted,
    BookingConfirmed,
    BookingCreated,
    BookingNoShow,
    BookingRescheduled,
    SlotReleased,
)
from app.modules.booking.exceptions import (
    BookingNotFoundError,
    HoldExpiredError,
    HoldNotFoundError,
    HorizonTooLargeError,
    ProviderLocationMismatchError,
    ProviderNotQualifiedError,
    SlotNotOfferedError,
    SlotUnavailableError,
)
from app.modules.booking.models import SlotHoldRecord
from app.modules.booking.repository import (
    BookingRepository,
    ScheduleRepository,
    SlotHoldRepository,
)
from app.modules.catalog.service import CatalogService
from app.modules.discovery.service import AttributionService
from app.modules.identity.service import CustomerService


class BookingService:
    def __init__(
        self,
        *,
        repository: BookingRepository,
        schedules: ScheduleRepository,
        holds: SlotHoldRepository,
        catalog: CatalogService,
        customers: CustomerService,
        tenant_id: UUID,
        secret_key: str,
        attribution: AttributionService | None = None,
        cancellation_policy: CancellationPolicy | None = None,
        slot_granularity_minutes: int = 15,
        max_horizon_days: int = 90,
        hold_ttl_seconds: int = 300,
    ) -> None:
        self.repository = repository
        self.schedules = schedules
        self.holds = holds
        # Booking reaches catalog and identity through their *services*, never
        # their repositories or models — that is the context boundary.
        self.catalog = catalog
        self.customers = customers
        # Discovery answers one question and no others: does this referral token
        # make the booking a marketplace booking (ADR-0010)? Optional because
        # every non-HTTP caller — the payment webhook, the outbox dispatcher,
        # unit tests — creates bookings that were never referred, and a booking
        # with no attribution is `direct_link`, the zero-commission default.
        self.attribution = attribution
        self.tenant_id = tenant_id
        self.secret_key = secret_key
        self.cancellation_policy = cancellation_policy or CancellationPolicy()
        self.slot_granularity_minutes = slot_granularity_minutes
        self.max_horizon_days = max_horizon_days
        self.hold_ttl_seconds = hold_ttl_seconds

    # --- availability -----------------------------------------------------

    async def set_provider_schedule(
        self, *, provider_id: UUID, windows: list[WorkingWindow]
    ) -> list[WorkingWindow]:
        """Replaces a provider's weekly working hours."""
        provider = await self.catalog.get_provider(provider_id)
        validate_windows(windows)
        return await self.schedules.replace_windows(
            provider_id=provider_id, location_id=provider.location_id, windows=windows
        )

    async def get_provider_schedule(self, provider_id: UUID) -> list[WorkingWindow]:
        await self.catalog.get_provider(provider_id)
        return await self.schedules.list_windows(provider_id)

    async def add_schedule_exception(
        self,
        *,
        provider_id: UUID,
        on_date,
        is_closed: bool = True,
        start_minute: int | None = None,
        end_minute: int | None = None,
        reason: str | None = None,
    ):
        await self.catalog.get_provider(provider_id)
        record = self.schedules.add_exception(
            provider_id=provider_id,
            on_date=on_date,
            is_closed=is_closed,
            start_minute=start_minute,
            end_minute=end_minute,
            reason=reason,
        )
        await self.schedules.session.flush()
        return record

    async def availability(
        self,
        *,
        provider_id: UUID,
        service_id: UUID,
        date_from: datetime,
        date_to: datetime,
        now: datetime | None = None,
    ) -> list[AvailabilitySlot]:
        """Bookable slots for one provider and service.

        Generated, never stored. The domain function is pure and the inputs are
        loaded here, which is what makes availability deterministic (docs/09 #4)
        rather than a cache that can drift out of step with the bookings table.

        Every returned slot carries a signed `slot_id`, so a later request — or
        an AI agent — can be checked against a slot the server actually offered
        instead of one it invented (docs/07 section 5).
        """
        now = now or datetime.now(UTC)

        if date_to <= date_from:
            raise ScheduleError("date_to must be after date_from.")
        if (date_to - date_from) > timedelta(days=self.max_horizon_days):
            raise HorizonTooLargeError(self.max_horizon_days)

        service = await self.catalog.get_service(service_id)
        provider = await self.catalog.get_provider(provider_id)
        location = await self.catalog.get_location(provider.location_id)

        if not await self.catalog.is_provider_qualified(provider_id, service_id):
            raise ProviderNotQualifiedError(provider_id, service_id)

        window = TimeRange(starts_at=date_from, ends_at=date_to)
        weekly = await self.schedules.list_windows(provider_id)
        exceptions = await self.schedules.list_exceptions(
            provider_id=provider_id,
            date_from=date_from.date(),
            date_to=date_to.date(),
        )

        # Bookings and live holds block identically: a slot someone is
        # mid-checkout on is not available, even though no booking exists yet.
        taken = await self.repository.list_blocking_in_window(
            provider_id=provider_id, window=window
        )
        taken += await self.holds.list_active(provider_id=provider_id, window=window, now=now)

        slots = generate_availability(
            weekly=weekly,
            exceptions=exceptions,
            taken=taken,
            provider_id=provider_id,
            service_id=service_id,
            location_id=location.id,
            timezone=location.timezone,
            date_from=date_from,
            date_to=date_to,
            duration_minutes=service.duration_minutes,
            granularity_minutes=self.slot_granularity_minutes,
            now=now,
        )

        return [
            AvailabilitySlot(
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                provider_id=slot.provider_id,
                service_id=slot.service_id,
                location_id=slot.location_id,
                slot_id=sign_slot_id(
                    tenant_id=self.tenant_id,
                    provider_id=slot.provider_id,
                    service_id=slot.service_id,
                    starts_at=slot.starts_at,
                    secret=self.secret_key,
                ),
            )
            for slot in slots
        ]

    def _assert_slot_was_offered(
        self, *, slot_id: str, provider_id: UUID, service_id: UUID, starts_at: datetime
    ) -> None:
        if not verify_slot_id(
            slot_id,
            tenant_id=self.tenant_id,
            provider_id=provider_id,
            service_id=service_id,
            starts_at=starts_at,
            secret=self.secret_key,
        ):
            raise SlotNotOfferedError()

    # --- holds ------------------------------------------------------------

    async def hold_slot(
        self,
        *,
        provider_id: UUID,
        service_id: UUID,
        starts_at: datetime,
        customer_id: UUID | None = None,
        slot_id: str | None = None,
        now: datetime | None = None,
    ) -> SlotHoldRecord:
        """Reserves a slot briefly while payment or confirmation completes.

        Required before an AI agent may proceed (docs/04 section 2A, docs/10
        section 5) and used by PWA checkout. Without it two customers can both
        reach the payment step for the same appointment, and one of them gets a
        refund and a bad memory of the salon.

        If `slot_id` is supplied it must verify — that is how an agent is
        prevented from holding a time the server never offered.
        """
        now = now or datetime.now(UTC)

        service = await self.catalog.get_service(service_id)
        provider = await self.catalog.get_provider(provider_id)

        if not await self.catalog.is_provider_qualified(provider_id, service_id):
            raise ProviderNotQualifiedError(provider_id, service_id)

        if slot_id is not None:
            self._assert_slot_was_offered(
                slot_id=slot_id,
                provider_id=provider_id,
                service_id=service_id,
                starts_at=starts_at,
            )

        slot = build_slot(starts_at=starts_at, duration_minutes=service.duration_minutes)
        assert_slot_is_bookable(slot, now=now)

        # Same lock as `create`: hold and booking contend for one calendar, so
        # they must serialise against each other, not just among themselves.
        await self.repository.lock_provider_calendar(provider_id)

        booked = await self.repository.find_conflicting(provider_id=provider_id, slot=slot)
        if booked is not None:
            raise SlotUnavailableError()
        held = await self.holds.find_conflicting(provider_id=provider_id, slot=slot, now=now)
        if held is not None:
            raise SlotUnavailableError()

        return await self.holds.add_hold(
            SlotHoldRecord(
                tenant_id=self.tenant_id,
                provider_id=provider_id,
                service_id=service_id,
                location_id=provider.location_id,
                customer_id=customer_id,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                # 32 bytes of urandom: this token is a bearer credential for the
                # slot, so it must not be guessable.
                hold_token=secrets.token_urlsafe(32)[:64],
                expires_at=now + timedelta(seconds=self.hold_ttl_seconds),
            )
        )

    async def release_hold(self, hold_token: str, *, now: datetime | None = None) -> None:
        hold = await self.holds.get_by_token(hold_token)
        if hold is None:
            raise HoldNotFoundError()
        hold.consumed_at = now or datetime.now(UTC)
        await self.holds.session.flush()

    async def _consume_hold(self, hold_token: str, *, slot: TimeRange, now: datetime):
        """Validates a hold covers the slot being booked, and burns it."""
        hold = await self.holds.get_by_token(hold_token)
        if hold is None:
            raise HoldNotFoundError()
        if hold.consumed_at is not None or hold.expires_at <= now:
            raise HoldExpiredError()
        if hold.starts_at != slot.starts_at or hold.ends_at != slot.ends_at:
            raise SlotNotOfferedError()
        hold.consumed_at = now
        return hold

    # --- create -----------------------------------------------------------

    async def create(
        self,
        *,
        location_id: UUID,
        service_id: UUID,
        provider_id: UUID,
        customer_reference_id: UUID,
        self_service: bool,
        starts_at: datetime,
        source: BookingSource = BookingSource.DIRECT_LINK,
        referral_token: str | None = None,
        notes: str | None = None,
        hold_token: str | None = None,
        slot_id: str | None = None,
        now: datetime | None = None,
    ) -> Booking:
        """Creates a booking.

        `customer_reference_id` is resolved by the caller from the authenticated
        principal (see `resolve_booking_customer`), never taken from a request
        body — a client must not be able to book in someone else's name.
        `self_service` says whether that id is the caller's own user id or a
        customer id staff named; `CustomerService` turns either into a real
        customer record.

        `source` is likewise resolved by the caller (`resolve_booking_source`)
        rather than taken from the body, because it decides what the salon is
        charged. It is written once here and never updated — reschedule and
        every status transition leave it alone (docs/11 section 4).

        `referral_token` is the one input that can change `source`, and it is
        resolved *here* rather than by the caller for a specific reason: proving
        a referral requires knowing which business is being booked, and that is
        not known until the location is read below. Doing it here keeps `source`
        written exactly once, at construction, which is what ADR-0008 means by
        calling it immutable.
        """
        now = now or datetime.now(UTC)
        # Minted up front rather than at construction below, so the referral
        # this booking consumes can record *which* booking claimed it. That
        # stamp is the audit trail behind a commission line, and it has to be
        # written in the same transaction as the booking or a rolled-back
        # booking leaves a referral marked spent.
        booking_id = uuid4()

        # 1. Ask catalog what we are booking. Duration and price come from the
        #    catalog record, never from the client.
        service = await self.catalog.get_service(service_id)
        provider = await self.catalog.get_provider(provider_id)
        location = await self.catalog.get_location(location_id)

        if provider.location_id != location.id or service.location_id != location.id:
            raise ProviderLocationMismatchError()

        if not await self.catalog.is_provider_qualified(provider_id, service_id):
            raise ProviderNotQualifiedError(provider_id, service_id)

        # 1b. Now the business is known, so ask whether NOVA can prove it
        #     introduced this customer. Only the unattributed default is ever
        #     upgraded: a booking the caller could legitimately declare as
        #     `whatsapp`, `walk_in` or `reception` arrived through a channel the
        #     salon owns, and a stray referral token must not re-label it as one
        #     NOVA is owed 35% on.
        if (
            source is BookingSource.DIRECT_LINK
            and referral_token
            and self.attribution is not None
            and await self.attribution.attributes_to_marketplace(
                referral_token,
                business_id=location.business_id,
                booking_id=booking_id,
                now=now,
            )
        ):
            source = BookingSource.MARKETPLACE

        # 2. Resolve who this is for. A booking with no customer record cannot
        #    be confirmed by WhatsApp or checked in at reception.
        customer = await self.customers.resolve_for_booking(
            customer_reference_id, self_service=self_service
        )

        # 3. Derive the slot and check it is legal.
        slot = build_slot(starts_at=starts_at, duration_minutes=service.duration_minutes)
        assert_slot_is_bookable(slot, now=now)

        if slot_id is not None:
            self._assert_slot_was_offered(
                slot_id=slot_id,
                provider_id=provider_id,
                service_id=service_id,
                starts_at=slot.starts_at,
            )

        # 4. Reject a double-booking.
        #    The advisory lock makes the read-then-insert below atomic for this
        #    provider: a concurrent request for the same provider blocks here
        #    until this transaction commits, so it cannot read a stale "no
        #    conflict". The EXCLUDE constraint remains as a backstop.
        await self.repository.lock_provider_calendar(provider_id)

        conflict = await self.repository.find_conflicting(provider_id=provider_id, slot=slot)
        if conflict is not None:
            raise SlotUnavailableError()

        # A hold this booking owns is consumed; a hold belonging to *someone
        # else* still blocks, which is the entire point of holding.
        if hold_token is not None:
            await self._consume_hold(hold_token, slot=slot, now=now)
        elif (
            await self.holds.find_conflicting(provider_id=provider_id, slot=slot, now=now)
            is not None
        ):
            raise SlotUnavailableError()

        booking = Booking(
            id=booking_id,
            tenant_id=self.tenant_id,
            business_id=location.business_id,
            location_id=location_id,
            service_id=service_id,
            provider_id=provider_id,
            customer_id=customer.id,
            slot=slot,
            price=Money(amount=service.price, currency=service.currency),
            source=source,
            notes=notes,
        )
        saved = await self.repository.add_booking(booking)

        await publish_event(
            self.repository.session,
            BookingCreated(
                tenant_id=self.tenant_id,
                booking_id=saved.id,
                customer_id=customer.id,
                starts_at=slot.starts_at,
            ),
        )
        return saved

    # --- transitions ------------------------------------------------------

    async def get(self, booking_id: UUID) -> Booking:
        booking = await self.repository.get_booking(booking_id)
        if booking is None:
            raise BookingNotFoundError(booking_id)
        return booking

    async def get_for_principal(self, booking_id: UUID, principal: Principal) -> Booking:
        """A booking the caller is entitled to see.

        Tenant scoping alone stopped being sufficient the moment a customer
        principal could reach any tenant: every booking in the salon was then
        one UUID away. This is the per-row half of that authorization.

        Staff see everything in their tenant — reception has to. A customer
        sees only bookings belonging to their own customer record here, found
        without provisioning one (`find_for_user`, not `resolve_for_booking`).

        Raises `BookingNotFoundError` — 404, not 403 — for someone else's
        booking. This deliberately differs from `require_tenant_access`, which
        answers 403 because ADR-0006 reasoned that tenant ids are not secrets
        and a clear error is more debuggable. A booking id is different: 403
        confirms the booking exists, which turns this endpoint into an
        enumeration oracle over every appointment on the platform. Under a
        per-row visibility model the honest answer is that the row is not in
        the caller's set.
        """
        booking = await self.get(booking_id)
        if principal.is_staff:
            return booking

        customer = await self.customers.find_for_user(principal.subject_id)
        if customer is None or customer.id != booking.customer_id:
            raise BookingNotFoundError(booking_id)
        return booking

    async def assert_visible_to(self, booking_id: UUID, principal: Principal) -> Booking:
        """`get_for_principal` read as a guard. Same rule, clearer at a call site
        that is about to mutate rather than return."""
        return await self.get_for_principal(booking_id, principal)

    async def confirm(self, booking_id: UUID) -> Booking:
        """Confirm a booking.

        Called by the payment webhook once funds are verified — not by the
        booking agent, which may only take a booking to PENDING_PAYMENT
        (docs/10 section 5).
        """
        booking = await self.get(booking_id)
        booking.confirm()
        saved = await self.repository.save(booking)

        await publish_event(
            self.repository.session,
            BookingConfirmed(
                tenant_id=self.tenant_id,
                booking_id=saved.id,
                customer_id=saved.customer_id,
                starts_at=saved.slot.starts_at,
            ),
        )
        return saved

    async def require_payment(self, booking_id: UUID) -> Booking:
        booking = await self.get(booking_id)
        booking.require_payment()
        return await self.repository.save(booking)

    async def cancel(
        self,
        booking_id: UUID,
        *,
        reason: str | None = None,
        by_staff: bool = False,
        now: datetime | None = None,
    ) -> Booking:
        booking = await self.get(booking_id)
        booking.cancel(
            policy=self.cancellation_policy,
            now=now or datetime.now(UTC),
            reason=reason,
            # Staff cancelling for the business (provider ill, salon closed)
            # must not be blocked by the customer-facing deadline.
            enforce_policy=not by_staff,
        )
        saved = await self.repository.save(booking)

        await publish_event(
            self.repository.session,
            BookingCancelled(
                tenant_id=self.tenant_id,
                booking_id=saved.id,
                customer_id=saved.customer_id,
                reason=reason,
            ),
        )
        await self._announce_released_slot(saved)
        return saved

    async def reschedule(
        self,
        booking_id: UUID,
        *,
        new_starts_at: datetime,
        provider_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Booking:
        """Moves a booking, re-running every check that guarded its creation.

        docs/07 section 6 declares this endpoint; it did not exist. Doing it as
        cancel-then-create would lose the booking id the customer already has on
        their ticket, and would briefly release the slot to whoever asked next.

        The old slot is only announced as released *after* the new one is
        secured, so a failed reschedule leaves the original booking intact.
        """
        now = now or datetime.now(UTC)
        booking = await self.get(booking_id)

        if not booking.occupies_calendar:
            raise SlotUnavailableError()

        target_provider_id = provider_id or booking.provider_id
        service = await self.catalog.get_service(booking.service_id)

        if target_provider_id != booking.provider_id:
            provider = await self.catalog.get_provider(target_provider_id)
            if provider.location_id != booking.location_id:
                raise ProviderLocationMismatchError()
            if not await self.catalog.is_provider_qualified(target_provider_id, booking.service_id):
                raise ProviderNotQualifiedError(target_provider_id, booking.service_id)

        new_slot = build_slot(starts_at=new_starts_at, duration_minutes=service.duration_minutes)
        assert_slot_is_bookable(new_slot, now=now)

        await self.repository.lock_provider_calendar(target_provider_id)

        conflict = await self.repository.find_conflicting(
            provider_id=target_provider_id,
            slot=new_slot,
            # Its own row must not count as a conflict with itself.
            exclude_booking_id=booking.id,
        )
        if conflict is not None:
            raise SlotUnavailableError()
        if (
            await self.holds.find_conflicting(
                provider_id=target_provider_id, slot=new_slot, now=now
            )
            is not None
        ):
            raise SlotUnavailableError()

        previous_slot = booking.slot
        previous_provider_id = booking.provider_id

        booking.slot = new_slot
        booking.provider_id = target_provider_id
        saved = await self.repository.reschedule_booking(booking, provider_id=target_provider_id)

        await publish_event(
            self.repository.session,
            BookingRescheduled(
                tenant_id=self.tenant_id,
                booking_id=saved.id,
                customer_id=saved.customer_id,
                previous_starts_at=previous_slot.starts_at,
                starts_at=saved.slot.starts_at,
            ),
        )
        await publish_event(
            self.repository.session,
            SlotReleased(
                tenant_id=self.tenant_id,
                provider_id=previous_provider_id,
                starts_at=previous_slot.starts_at,
                ends_at=previous_slot.ends_at,
            ),
        )
        return saved

    async def check_in(self, booking_id: UUID) -> Booking:
        booking = await self.get(booking_id)
        booking.check_in()
        return await self.repository.save(booking)

    async def start_service(self, booking_id: UUID) -> Booking:
        booking = await self.get(booking_id)
        booking.start_service()
        return await self.repository.save(booking)

    async def complete(self, booking_id: UUID) -> Booking:
        booking = await self.get(booking_id)
        booking.complete()
        saved = await self.repository.save(booking)

        await publish_event(
            self.repository.session,
            BookingCompleted(
                tenant_id=self.tenant_id,
                booking_id=saved.id,
                customer_id=saved.customer_id,
            ),
        )
        return saved

    async def mark_no_show(self, booking_id: UUID) -> Booking:
        booking = await self.get(booking_id)
        booking.mark_no_show()
        saved = await self.repository.save(booking)

        await publish_event(
            self.repository.session,
            BookingNoShow(
                tenant_id=self.tenant_id,
                booking_id=saved.id,
                customer_id=saved.customer_id,
            ),
        )
        await self._announce_released_slot(saved)
        return saved

    # --- reads ------------------------------------------------------------

    async def list_for_customer(
        self, customer_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[Booking]:
        return await self.repository.list_for_customer(
            customer_id=customer_id, limit=limit, offset=offset
        )

    async def list_for_customer_reference(
        self,
        reference_id: UUID,
        *,
        self_service: bool,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Booking]:
        """Same reference-resolution as `create`, for the list endpoint.

        Exists so the router never has to reach through this service into
        `CustomerService` itself — routers call one service, and the
        architecture test enforces it.
        """
        customer = await self.customers.resolve_for_booking(reference_id, self_service=self_service)
        return await self.repository.list_for_customer(
            customer_id=customer.id, limit=limit, offset=offset
        )

    async def list_for_provider(
        self, provider_id: UUID, *, date_from: datetime, date_to: datetime
    ) -> list[Booking]:
        window = TimeRange(starts_at=date_from, ends_at=date_to)
        return await self.repository.list_for_provider(provider_id=provider_id, window=window)

    async def list_due_for_no_show(self, *, before: datetime) -> list[Booking]:
        return await self.repository.list_due_for_no_show(before=before)

    async def businesses_for(self, booking_ids: Sequence[UUID]) -> dict[UUID, UUID]:
        """Which business each of these bookings belongs to.

        For the daily payout job: a payment knows its booking and nothing else,
        but money is paid to a business. Cross-module lookups go service to
        service, so billing asks booking rather than joining to its table.
        """
        return await self.repository.map_business_ids(booking_ids)

    # --- analytics facts (docs/13 section 6.2) ----------------------------

    async def list_booking_facts(
        self, *, business_id: UUID, window: TimeRange, limit: int
    ) -> list[BookingFact]:
        return await self.repository.list_facts(business_id=business_id, window=window, limit=limit)

    async def list_customer_visit_facts(
        self, *, business_id: UUID, as_of: datetime, limit: int
    ) -> list[CustomerVisitFact]:
        return await self.repository.list_customer_visit_facts(
            business_id=business_id, as_of=as_of, limit=limit
        )

    async def list_capacity_facts(
        self, *, provider_ids: Sequence[UUID], date_from: date, date_to: date
    ) -> list[ProviderCapacityFact]:
        """Each provider's weekly hours and the exceptions inside a date range."""
        weekly = await self.schedules.list_windows_for_providers(provider_ids)
        facts: list[ProviderCapacityFact] = []
        for provider_id in provider_ids:
            exceptions = await self.schedules.list_exceptions(
                provider_id=provider_id, date_from=date_from, date_to=date_to
            )
            facts.append(
                ProviderCapacityFact(
                    provider_id=provider_id,
                    weekly=tuple(weekly.get(provider_id, [])),
                    exceptions=tuple(exceptions.values()),
                )
            )
        return facts

    # --- internals --------------------------------------------------------

    async def _announce_released_slot(self, booking: Booking) -> None:
        await publish_event(
            self.repository.session,
            SlotReleased(
                tenant_id=self.tenant_id,
                provider_id=booking.provider_id,
                starts_at=booking.slot.starts_at,
                ends_at=booking.slot.ends_at,
            ),
        )


__all__ = ["BookingService", "BookingStatus"]
