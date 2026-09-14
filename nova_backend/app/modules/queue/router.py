"""queue · DELIVERY layer — HTTP.

Layer rule: schemas, service, dependencies. No business rules here.

Note there is no "set queue position" endpoint. Ordering is derived by the
domain from arrival and appointment times (docs/08 section 12: queue ordering
must be deterministic); an endpoint that let reception reorder the line by hand
would make that untrue on the first busy Thursday.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.idempotency import IdempotencyGuard, idempotency_guard
from app.core.pagination import PageParams
from app.core.schemas import Page
from app.core.security import Principal, get_principal, require_staff
from app.core.throttling import write_rate_limit
from app.modules.booking.dependencies import resolve_booking_customer
from app.modules.queue.dependencies import get_queue_service
from app.modules.queue.domain import QueueEntry
from app.modules.queue.schemas import (
    CheckInResultOut,
    CheckInTicketRequest,
    CreateQueueRequest,
    IssueTicketRequest,
    JoinQueueRequest,
    QueueEntryOut,
    QueueOut,
    SetQueueOpenRequest,
    TicketOut,
    TicketStateOut,
)
from app.modules.queue.service import QueuePosition, QueueService

router = APIRouter(prefix="/tenants/{tenant_id}/queues", tags=["queue"])


def _entry_out(entry: QueueEntry, position: QueuePosition | None = None) -> QueueEntryOut:
    return QueueEntryOut(
        id=entry.id,
        queue_id=entry.queue_id,
        location_id=entry.location_id,
        customer_id=entry.customer_id,
        service_id=entry.service_id,
        provider_id=entry.provider_id,
        status=entry.status,
        source=entry.source,
        position=entry.position,
        party_size=entry.party_size,
        booking_id=entry.booking_id,
        joined_at=entry.joined_at,
        called_at=entry.called_at,
        place_in_line=position.place_in_line if position else None,
        estimated_wait_minutes=position.estimated_wait_minutes if position else None,
    )


# --- queue administration -------------------------------------------------


@router.post(
    "",
    response_model=QueueOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def create_queue(
    tenant_id: UUID,
    payload: CreateQueueRequest,
    session: AsyncSession = Depends(get_db_session),
    service: QueueService = Depends(get_queue_service),
) -> object:
    queue = await service.create_queue(**payload.model_dump())
    await session.commit()
    return queue


@router.get("", response_model=Page[QueueOut])
async def list_queues(
    tenant_id: UUID,
    location_id: UUID,
    service: QueueService = Depends(get_queue_service),
) -> Page[QueueOut]:
    rows = await service.list_queues(location_id)
    return Page(items=[QueueOut.model_validate(r) for r in rows])


@router.patch(
    "/{queue_id}/open",
    response_model=QueueOut,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def set_queue_open(
    tenant_id: UUID,
    queue_id: UUID,
    payload: SetQueueOpenRequest,
    session: AsyncSession = Depends(get_db_session),
    service: QueueService = Depends(get_queue_service),
) -> object:
    """Closing a queue stops new joins; people already waiting are still served."""
    queue = await service.set_queue_open(queue_id, is_open=payload.is_open)
    await session.commit()
    return queue


# --- the line -------------------------------------------------------------


@router.post(
    "/{queue_id}/entries",
    response_model=QueueEntryOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(write_rate_limit)],
)
async def join_queue(
    tenant_id: UUID,
    queue_id: UUID,
    payload: JoinQueueRequest,
    session: AsyncSession = Depends(get_db_session),
    service: QueueService = Depends(get_queue_service),
    principal: Principal = Depends(get_principal),
    guard: IdempotencyGuard = Depends(idempotency_guard("POST /queues/entries")),
) -> object:
    fields = payload.model_dump()
    on_behalf_of = fields.pop("on_behalf_of_customer_id")
    customer_reference_id = resolve_booking_customer(on_behalf_of, principal)

    replay = await guard.begin({**fields, "queue_id": str(queue_id)})
    if replay is not None:
        return replay

    position = await service.join(
        queue_id=queue_id,
        customer_reference_id=customer_reference_id,
        self_service=on_behalf_of is None,
        **fields,
    )
    out = _entry_out(position.entry, position)
    await guard.complete(status_code=status.HTTP_201_CREATED, body=out.model_dump(mode="json"))
    await session.commit()
    return out


@router.get("/{queue_id}/entries", response_model=Page[QueueEntryOut])
async def list_queue_entries(
    tenant_id: UUID,
    queue_id: UUID,
    params: PageParams = Depends(),
    service: QueueService = Depends(get_queue_service),
    _: Principal = Depends(require_staff),
) -> Page[QueueEntryOut]:
    """The live line. Staff-only: it names every waiting customer."""
    entries = await service.list_queue(queue_id)
    window = entries[params.offset : params.offset + params.limit]
    return Page(items=[_entry_out(e) for e in window], total=len(entries))


@router.get("/entries/{entry_id}", response_model=QueueEntryOut)
async def get_queue_entry(
    tenant_id: UUID,
    entry_id: UUID,
    service: QueueService = Depends(get_queue_service),
    principal: Principal = Depends(get_principal),
) -> QueueEntryOut:
    """A customer polling "how much longer?" — the one read they need.

    Their own entry only. The list endpoint above is staff-only because it
    names every waiting customer; reading them one at a time would defeat that.
    """
    await service.assert_entry_visible_to(entry_id, principal)
    position = await service.position_of(entry_id)
    return _entry_out(position.entry, position)


@router.post(
    "/{queue_id}/call-next",
    response_model=QueueEntryOut,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def call_next(
    tenant_id: UUID,
    queue_id: UUID,
    provider_id: UUID | None = None,
    session: AsyncSession = Depends(get_db_session),
    service: QueueService = Depends(get_queue_service),
) -> QueueEntryOut:
    entry = await service.call_next(queue_id, provider_id=provider_id)
    await session.commit()
    return _entry_out(entry)


@router.post(
    "/entries/{entry_id}/missed",
    response_model=QueueEntryOut,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def mark_missed(
    tenant_id: UUID,
    entry_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: QueueService = Depends(get_queue_service),
) -> QueueEntryOut:
    entry = await service.mark_missed(entry_id)
    await session.commit()
    return _entry_out(entry)


@router.post(
    "/entries/{entry_id}/requeue",
    response_model=QueueEntryOut,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def requeue(
    tenant_id: UUID,
    entry_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: QueueService = Depends(get_queue_service),
) -> QueueEntryOut:
    """Someone who stepped outside and came back, rather than losing them."""
    entry = await service.requeue(entry_id)
    await session.commit()
    return _entry_out(entry)


@router.post(
    "/entries/{entry_id}/start",
    response_model=QueueEntryOut,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def start_service(
    tenant_id: UUID,
    entry_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: QueueService = Depends(get_queue_service),
) -> QueueEntryOut:
    entry = await service.start_service(entry_id)
    await session.commit()
    return _entry_out(entry)


@router.post(
    "/entries/{entry_id}/complete",
    response_model=QueueEntryOut,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def complete_entry(
    tenant_id: UUID,
    entry_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: QueueService = Depends(get_queue_service),
) -> QueueEntryOut:
    entry = await service.complete(entry_id)
    await session.commit()
    return _entry_out(entry)


@router.post(
    "/entries/{entry_id}/cancel",
    response_model=QueueEntryOut,
    dependencies=[Depends(write_rate_limit)],
)
async def cancel_entry(
    tenant_id: UUID,
    entry_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: QueueService = Depends(get_queue_service),
    principal: Principal = Depends(get_principal),
) -> QueueEntryOut:
    """A customer leaving the line themselves, or staff removing them.

    Themselves being the operative word: unguarded, one authenticated account
    could empty a salon's queue on a busy Thursday.
    """
    await service.assert_entry_visible_to(entry_id, principal)
    entry = await service.cancel(entry_id)
    await session.commit()
    return _entry_out(entry)


# --- tickets --------------------------------------------------------------

ticket_router = APIRouter(prefix="/tenants/{tenant_id}/tickets", tags=["queue"])


@ticket_router.post(
    "",
    response_model=TicketOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(write_rate_limit)],
)
async def issue_ticket(
    tenant_id: UUID,
    payload: IssueTicketRequest,
    session: AsyncSession = Depends(get_db_session),
    service: QueueService = Depends(get_queue_service),
    principal: Principal = Depends(get_principal),
) -> TicketOut:
    """Issues a QR ticket for the caller's own booking or queue entry.

    The ownership check is not decoration. Issuing revokes any existing valid
    ticket for the same subject, so without it any authenticated account could
    name a stranger's booking, invalidate the QR code that person is holding at
    the counter, and receive a working replacement for their appointment.
    """
    await service.assert_ticket_subject_visible_to(
        principal,
        booking_id=payload.booking_id,
        queue_entry_id=payload.queue_entry_id,
    )
    issued = await service.issue_ticket(**payload.model_dump())
    await session.commit()
    return TicketOut(
        id=issued.ticket.id,
        ticket_code=issued.ticket.ticket_code,
        qr_payload=issued.qr_payload,
        status=issued.ticket.status,
        expires_at=issued.ticket.expires_at,
        ticket_page_url=issued.ticket_page_url,
    )


@ticket_router.post(
    "/check-in",
    response_model=CheckInResultOut,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def check_in_with_ticket(
    tenant_id: UUID,
    payload: CheckInTicketRequest,
    session: AsyncSession = Depends(get_db_session),
    service: QueueService = Depends(get_queue_service),
) -> CheckInResultOut:
    """Reception scans a QR ticket (docs/09 #8).

    Staff-only and rate-limited: this endpoint tells the caller whether a given
    payload is valid, so leaving it open would make it an oracle for brute
    force.
    """
    ticket, entry = await service.redeem_ticket(qr_payload=payload.qr_payload)
    await session.commit()
    return CheckInResultOut(
        ticket=TicketStateOut.model_validate(ticket),
        entry=_entry_out(entry) if entry is not None else None,
    )


@ticket_router.post(
    "/{ticket_id}/revoke",
    response_model=TicketStateOut,
    dependencies=[Depends(require_staff), Depends(write_rate_limit)],
)
async def revoke_ticket(
    tenant_id: UUID,
    ticket_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: QueueService = Depends(get_queue_service),
) -> object:
    ticket = await service.revoke_ticket(ticket_id)
    await session.commit()
    return ticket
