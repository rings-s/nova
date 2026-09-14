"""booking · DELIVERY layer — DI providers."""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session, get_tenant_context
from app.core.security import AuthorizationError, Principal
from app.modules.booking.domain import BookingSource, CancellationPolicy
from app.modules.booking.repository import (
    BookingRepository,
    ScheduleRepository,
    SlotHoldRepository,
)
from app.modules.booking.service import BookingService
from app.modules.catalog.dependencies import build_catalog_service, get_catalog_service
from app.modules.catalog.service import CatalogService
from app.modules.discovery.dependencies import build_attribution_service
from app.modules.discovery.service import AttributionService
from app.modules.identity.dependencies import (
    build_customer_service,
    get_customer_service,
)
from app.modules.identity.service import CustomerService


def build_booking_service(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    catalog: CatalogService | None = None,
    customers: CustomerService | None = None,
    attribution: AttributionService | None = None,
) -> BookingService:
    """Assembles the service outside the request DI graph.

    The payment webhook needs a BookingService but has no bearer token, so it
    cannot resolve `get_tenant_context`. Without this factory that path would
    hand-roll the same wiring and drift out of step with the provider below.
    """
    settings = get_settings()
    return BookingService(
        repository=BookingRepository(session, tenant_id),
        schedules=ScheduleRepository(session, tenant_id),
        holds=SlotHoldRepository(session, tenant_id),
        catalog=catalog or build_catalog_service(session, tenant_id),
        customers=customers or build_customer_service(session, tenant_id),
        attribution=attribution or build_attribution_service(session, tenant_id),
        tenant_id=tenant_id,
        secret_key=settings.secret_key,
        cancellation_policy=CancellationPolicy(
            free_cancellation_hours=settings.booking_free_cancellation_hours
        ),
        slot_granularity_minutes=settings.availability_slot_granularity_minutes,
        max_horizon_days=settings.availability_max_horizon_days,
        hold_ttl_seconds=settings.slot_hold_ttl_seconds,
        max_active_holds_per_customer=settings.slot_hold_max_active_per_customer,
    )


def get_booking_service(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: UUID = Depends(get_tenant_context),
    catalog: CatalogService = Depends(get_catalog_service),
    customers: CustomerService = Depends(get_customer_service),
) -> BookingService:
    """Composes booking with catalog and identity.

    All of them share the same `session` (FastAPI caches `get_db_session` per
    request), so a booking, the customer record it provisions, and the outbox
    event it raises commit or roll back together.
    """
    return build_booking_service(session, tenant_id, catalog=catalog, customers=customers)


def resolve_booking_customer(
    on_behalf_of_customer_id: UUID | None,
    principal: Principal,
) -> UUID:
    """Decides whose booking this is.

    A customer books only for themselves. Staff (reception, or a service
    principal processing a webhook) may book on behalf of a named customer.

    This exists because `customer_id` used to be an ordinary field on the
    request body, which meant any caller could create or list bookings under
    any customer's identity.

    Returns an id whose *meaning* depends on which branch was taken — the
    caller's own user id, or a named customer id. `CustomerService.
    resolve_for_booking` is where that ambiguity is resolved into a record.
    """
    if on_behalf_of_customer_id is None:
        return principal.subject_id

    if not principal.is_staff:
        raise AuthorizationError("Only staff may book on behalf of another customer.")

    return on_behalf_of_customer_id


#: Sources a request body may declare. `MARKETPLACE` is absent on purpose: it
#: is the only chargeable source, so a client able to claim it could invent
#: revenue, and a client able to withhold it could avoid a charge it owes.
#:
#: It stays absent now that the discovery surface exists (ADR-0010). The
#: marketplace does not *declare* the source either — it presents a referral
#: token NOVA issued, and `BookingService.create` derives `MARKETPLACE` only
#: after looking that token up, checking it was issued for this business, and
#: checking it is inside the 30-day window (docs/11 section 3 rule 4). The
#: claim is server-side and falsifiable, which is exactly what ADR-0008
#: required before this value could ever be written.
CLIENT_DECLARABLE_SOURCES: frozenset[BookingSource] = frozenset(
    {
        BookingSource.DIRECT_LINK,
        BookingSource.WHATSAPP,
        BookingSource.WALK_IN,
        BookingSource.AI_AGENT,
    }
)


def resolve_booking_source(
    requested: BookingSource | None,
    principal: Principal,
    *,
    on_behalf_of: bool,
) -> BookingSource:
    """Decides which channel this booking is attributed to.

    Money depends on the answer, so it follows the same rule as
    `resolve_booking_customer`: take from the request only what the request is
    entitled to assert, and derive the rest from the authenticated principal.

    - Staff booking on behalf of someone is `RECEPTION`, whatever the body says.
      Reception is a counter action; nothing else it could claim is true.
    - A customer may declare how they reached the salon, but not `MARKETPLACE`
      and not `RECEPTION`.
    - Anything unstated is `DIRECT_LINK`, the zero-commission default. Guessing
      wrong in this direction under-bills NOVA; guessing wrong the other way
      charges a salon for a customer it already had, which docs/11 calls a P1.
    """
    if on_behalf_of and principal.is_staff:
        return BookingSource.RECEPTION

    if requested is None:
        return BookingSource.DIRECT_LINK

    if requested not in CLIENT_DECLARABLE_SOURCES:
        raise AuthorizationError(f"A booking request may not declare source '{requested}'.")

    return requested
