"""booking · DELIVERY layer — HTTP.

Layer rule: schemas, service, dependencies. No business rules here.

Note there is no "update booking status" endpoint taking an arbitrary status.
Each transition is its own verb, so an invalid move is unrepresentable at the
API surface rather than caught later in the domain.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.idempotency import IdempotencyGuard, idempotency_guard
from app.core.pagination import PageParams
from app.core.schemas import Page
from app.core.security import Principal, get_principal, require_staff
from app.core.throttling import default_rate_limit, write_rate_limit
from app.modules.booking.dependencies import (
    get_booking_service,
    resolve_booking_customer,
    resolve_booking_source,
)
from app.modules.booking.domain import Booking, WorkingWindow
from app.modules.booking.schemas import (
    AvailableSlotOut,
    BookingOut,
    CancelBookingRequest,
    CreateBookingRequest,
    HoldSlotRequest,
    HoldSlotResult,
    RescheduleBookingRequest,
    ScheduleExceptionOut,
    ScheduleExceptionRequest,
    ScheduleOut,
    SetScheduleRequest,
    WorkingWindowIn,
)
from app.modules.booking.service import BookingService

router = APIRouter(prefix="/tenants/{tenant_id}/bookings", tags=["booking"])


def _as_out(b: Booking) -> dict:
    """Flattens the domain entity's value objects into the flat API contract."""
    return {
        "id": b.id,
        "tenant_id": b.tenant_id,
        "business_id": b.business_id,
        "location_id": b.location_id,
        "service_id": b.service_id,
        "provider_id": b.provider_id,
        "customer_id": b.customer_id,
        "starts_at": b.slot.starts_at,
        "ends_at": b.slot.ends_at,
        "price": b.price.amount,
        "currency": b.price.currency,
        "status": b.status,
        "source": b.source,
        "cancellation_reason": b.cancellation_reason,
        "notes": b.notes,
    }


# --- availability ---------------------------------------------------------


@router.get(
    "/availability",
    response_model=Page[AvailableSlotOut],
    # Availability is necessarily open — a customer has to see free slots
    # before they can book one. But it is also a calendar-occupancy oracle:
    # polled hard enough it reveals exactly when a named provider is busy. The
    # limit does not close that, it bounds it.
    dependencies=[Depends(default_rate_limit)],
)
async def get_availability(
    tenant_id: UUID,
    provider_id: UUID = Query(...),
    service_id: UUID = Query(...),
    date_from: datetime = Query(...),
    date_to: datetime = Query(...),
    service: BookingService = Depends(get_booking_service),
) -> Page[AvailableSlotOut]:
    """Bookable slots, generated from the provider's schedule.

    Declared before `/{booking_id}` so the literal path wins the match — the
    other order makes "availability" parse as a booking id and 422.
    """
    slots = await service.availability(
        provider_id=provider_id,
        service_id=service_id,
        date_from=date_from,
        date_to=date_to,
    )
    return Page(
        items=[
            AvailableSlotOut(
                slot_id=s.slot_id,
                provider_id=s.provider_id,
                location_id=s.location_id,
                service_id=s.service_id,
                starts_at=s.starts_at,
                ends_at=s.ends_at,
            )
            for s in slots
        ],
        total=len(slots),
    )


@router.post(
    "/holds",
    response_model=HoldSlotResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(write_rate_limit)],
)
async def hold_slot(
    tenant_id: UUID,
    payload: HoldSlotRequest,
    session: AsyncSession = Depends(get_db_session),
    service: BookingService = Depends(get_booking_service),
) -> HoldSlotResult:
    """Reserves a slot for a few minutes while checkout completes."""
    hold = await service.hold_slot(**payload.model_dump())
    await session.commit()
    return HoldSlotResult(
        hold_token=hold.hold_token,
        provider_id=hold.provider_id,
        service_id=hold.service_id,
        starts_at=hold.starts_at,
        ends_at=hold.ends_at,
        expires_at=hold.expires_at,
    )


@router.delete(
    "/holds/{hold_token}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(write_rate_limit)],
)
async def release_slot_hold(
    tenant_id: UUID,
    hold_token: str,
    session: AsyncSession = Depends(get_db_session),
    service: BookingService = Depends(get_booking_service),
) -> None:
    """Abandoned checkout: give the slot back rather than waiting for expiry."""
    await service.release_hold(hold_token)
    await session.commit()


# --- schedules ------------------------------------------------------------
#
# Staff-only: a customer must not be able to rewrite when a salon is open.

schedule_router = APIRouter(prefix="/tenants/{tenant_id}/schedules", tags=["booking"])


@schedule_router.put(
    "/providers/{provider_id}",
    response_model=ScheduleOut,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def set_provider_schedule(
    tenant_id: UUID,
    provider_id: UUID,
    payload: SetScheduleRequest,
    session: AsyncSession = Depends(get_db_session),
    service: BookingService = Depends(get_booking_service),
) -> ScheduleOut:
    windows = await service.set_provider_schedule(
        provider_id=provider_id,
        windows=[
            WorkingWindow(weekday=w.weekday, start_minute=w.start_minute, end_minute=w.end_minute)
            for w in payload.windows
        ],
    )
    await session.commit()
    return ScheduleOut(
        provider_id=provider_id,
        windows=[
            WorkingWindowIn(weekday=w.weekday, start_minute=w.start_minute, end_minute=w.end_minute)
            for w in windows
        ],
    )


@schedule_router.get("/providers/{provider_id}", response_model=ScheduleOut)
async def get_provider_schedule(
    tenant_id: UUID,
    provider_id: UUID,
    service: BookingService = Depends(get_booking_service),
) -> ScheduleOut:
    windows = await service.get_provider_schedule(provider_id)
    return ScheduleOut(
        provider_id=provider_id,
        windows=[
            WorkingWindowIn(weekday=w.weekday, start_minute=w.start_minute, end_minute=w.end_minute)
            for w in windows
        ],
    )


@schedule_router.post(
    "/providers/{provider_id}/exceptions",
    response_model=ScheduleExceptionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def add_schedule_exception(
    tenant_id: UUID,
    provider_id: UUID,
    payload: ScheduleExceptionRequest,
    session: AsyncSession = Depends(get_db_session),
    service: BookingService = Depends(get_booking_service),
) -> ScheduleExceptionOut:
    """Eid, a holiday, or one stylist's afternoon off."""
    record = await service.add_schedule_exception(provider_id=provider_id, **payload.model_dump())
    await session.commit()
    return ScheduleExceptionOut.model_validate(record)


# --- bookings -------------------------------------------------------------


@router.post(
    "",
    response_model=BookingOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(write_rate_limit)],
)
async def create_booking(
    tenant_id: UUID,
    payload: CreateBookingRequest,
    session: AsyncSession = Depends(get_db_session),
    service: BookingService = Depends(get_booking_service),
    principal: Principal = Depends(get_principal),
    guard: IdempotencyGuard = Depends(idempotency_guard("POST /bookings")),
) -> Any:
    """Creates a booking.

    Send an `Idempotency-Key` header: a customer on a flaky connection tapping
    "Book" twice, or a client retrying a request whose response was lost,
    otherwise gets two appointments.

    `referral_token` stays in `fields` and is handed to the service rather than
    resolved here, unlike `source` and the customer. It is not a claim the
    request is making about itself — it is a credential NOVA issued, and
    verifying it needs the business id, which only the service knows once it
    has read the location.
    """
    fields = payload.model_dump()
    on_behalf_of = fields.pop("on_behalf_of_customer_id")
    customer_reference_id = resolve_booking_customer(on_behalf_of, principal)
    # Attribution decides what the salon is charged, so it is resolved here
    # from the principal rather than trusted from the body.
    fields["source"] = resolve_booking_source(
        fields.pop("source"), principal, on_behalf_of=on_behalf_of is not None
    )

    replay = await guard.begin(fields)
    if replay is not None:
        return replay

    booking = await service.create(
        **fields,
        customer_reference_id=customer_reference_id,
        self_service=on_behalf_of is None,
    )
    out = _as_out(booking)
    await guard.complete(status_code=status.HTTP_201_CREATED, body=out)
    await session.commit()
    return out


@router.get("/{booking_id}", response_model=BookingOut)
async def get_booking(
    tenant_id: UUID,
    booking_id: UUID,
    service: BookingService = Depends(get_booking_service),
    principal: Principal = Depends(get_principal),
) -> dict:
    """One booking, if it is the caller's.

    Staff see any booking in their tenant; a customer sees only their own, and
    gets a 404 otherwise rather than a 403 that would confirm the id exists.
    """
    return _as_out(await service.get_for_principal(booking_id, principal))


@router.get("", response_model=Page[BookingOut])
async def list_customer_bookings(
    tenant_id: UUID,
    customer_id: UUID | None = Query(
        default=None, description="Staff only. Defaults to the authenticated customer."
    ),
    params: PageParams = Depends(),
    service: BookingService = Depends(get_booking_service),
    principal: Principal = Depends(get_principal),
) -> Page[BookingOut]:
    # Same rule as creation: a customer sees only their own bookings. Without
    # this, `?customer_id=<anyone>` was a full read of another person's history.
    reference_id = resolve_booking_customer(customer_id, principal)

    bookings = await service.list_for_customer_reference(
        reference_id,
        self_service=customer_id is None,
        limit=params.limit,
        offset=params.offset,
    )
    return Page(items=[BookingOut(**_as_out(b)) for b in bookings])


@router.get(
    "/calendar/{provider_id}",
    response_model=Page[BookingOut],
    dependencies=[Depends(require_staff)],
)
async def list_provider_calendar(
    tenant_id: UUID,
    provider_id: UUID,
    date_from: datetime = Query(...),
    date_to: datetime = Query(...),
    service: BookingService = Depends(get_booking_service),
) -> Page[BookingOut]:
    """The day sheet. Staff-only — it exposes every customer at that branch."""
    bookings = await service.list_for_provider(provider_id, date_from=date_from, date_to=date_to)
    return Page(items=[BookingOut(**_as_out(b)) for b in bookings])


@router.post(
    "/{booking_id}/confirm",
    response_model=BookingOut,
    dependencies=[Depends(write_rate_limit)],
)
async def confirm_booking(
    tenant_id: UUID,
    booking_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: BookingService = Depends(get_booking_service),
    _: Principal = Depends(require_staff),
) -> dict:
    """Manual confirmation, for a salon not taking deposits.

    The normal path is the verified Moyasar webhook; this is staff overriding
    it, never the AI agent (docs/10 section 5).
    """
    booking = await service.confirm(booking_id)
    await session.commit()
    return _as_out(booking)


@router.post(
    "/{booking_id}/cancel",
    response_model=BookingOut,
    dependencies=[Depends(write_rate_limit)],
)
async def cancel_booking(
    tenant_id: UUID,
    booking_id: UUID,
    payload: CancelBookingRequest,
    by_staff: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    service: BookingService = Depends(get_booking_service),
    principal: Principal = Depends(get_principal),
) -> dict:
    # `by_staff` waives the cancellation deadline, so it has to be *proved*,
    # not asserted: as a bare query parameter any customer could set it and
    # cancel a same-day booking for free.
    waive_policy = by_staff and principal.is_staff
    # Ownership is a separate question from policy waiver, and only the second
    # was ever checked here: any caller who could reach the tenant could cancel
    # any booking in it, they just could not skip the deadline while doing so.
    await service.assert_visible_to(booking_id, principal)
    booking = await service.cancel(booking_id, reason=payload.reason, by_staff=waive_policy)
    await session.commit()
    return _as_out(booking)


@router.post(
    "/{booking_id}/reschedule",
    response_model=BookingOut,
    dependencies=[Depends(write_rate_limit)],
)
async def reschedule_booking(
    tenant_id: UUID,
    booking_id: UUID,
    payload: RescheduleBookingRequest,
    session: AsyncSession = Depends(get_db_session),
    service: BookingService = Depends(get_booking_service),
    principal: Principal = Depends(get_principal),
) -> dict:
    """Moves a booking, keeping its id — and therefore the customer's ticket.

    At least as sensitive as cancelling: a moved appointment is less visible to
    the person who booked it than a cancelled one, so they may simply not turn
    up. This route previously took no principal at all.
    """
    await service.assert_visible_to(booking_id, principal)
    booking = await service.reschedule(
        booking_id,
        new_starts_at=payload.new_starts_at,
        provider_id=payload.provider_id,
    )
    await session.commit()
    return _as_out(booking)


@router.post(
    "/{booking_id}/check-in",
    response_model=BookingOut,
    dependencies=[Depends(write_rate_limit)],
)
async def check_in_booking(
    tenant_id: UUID,
    booking_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: BookingService = Depends(get_booking_service),
    _: Principal = Depends(require_staff),
) -> dict:
    booking = await service.check_in(booking_id)
    await session.commit()
    return _as_out(booking)


@router.post(
    "/{booking_id}/start",
    response_model=BookingOut,
    dependencies=[Depends(write_rate_limit)],
)
async def start_booking_service(
    tenant_id: UUID,
    booking_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: BookingService = Depends(get_booking_service),
    _: Principal = Depends(require_staff),
) -> dict:
    booking = await service.start_service(booking_id)
    await session.commit()
    return _as_out(booking)


@router.post(
    "/{booking_id}/complete",
    response_model=BookingOut,
    dependencies=[Depends(write_rate_limit)],
)
async def complete_booking(
    tenant_id: UUID,
    booking_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: BookingService = Depends(get_booking_service),
    _: Principal = Depends(require_staff),
) -> dict:
    booking = await service.complete(booking_id)
    await session.commit()
    return _as_out(booking)


@router.post(
    "/{booking_id}/no-show",
    response_model=BookingOut,
    dependencies=[Depends(write_rate_limit)],
)
async def mark_booking_no_show(
    tenant_id: UUID,
    booking_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: BookingService = Depends(get_booking_service),
    _: Principal = Depends(require_staff),
) -> dict:
    booking = await service.mark_no_show(booking_id)
    await session.commit()
    return _as_out(booking)
