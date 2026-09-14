"""queue · DELIVERY layer — DI providers."""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session, get_tenant_context
from app.modules.booking.dependencies import build_booking_service, get_booking_service
from app.modules.booking.service import BookingService
from app.modules.catalog.dependencies import build_catalog_service, get_catalog_service
from app.modules.catalog.service import CatalogService
from app.modules.identity.dependencies import build_customer_service, get_customer_service
from app.modules.identity.service import CustomerService
from app.modules.queue.repository import (
    QueueEntryRepository,
    QueueRepository,
    TicketRepository,
)
from app.modules.queue.service import QueueService


def build_queue_service(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    catalog: CatalogService | None = None,
    customers: CustomerService | None = None,
    bookings: BookingService | None = None,
) -> QueueService:
    """Assembles the service outside the request DI graph.

    The analytics context and the worker need a QueueService without an
    authenticated tenant context; this keeps their wiring identical to the
    request path's instead of hand-rolling it.
    """
    settings = get_settings()
    catalog = catalog or build_catalog_service(session, tenant_id)
    customers = customers or build_customer_service(session, tenant_id)
    return QueueService(
        queues=QueueRepository(session, tenant_id),
        entries=QueueEntryRepository(session, tenant_id),
        tickets=TicketRepository(session, tenant_id),
        catalog=catalog,
        customers=customers,
        bookings=bookings
        or build_booking_service(session, tenant_id, catalog=catalog, customers=customers),
        tenant_id=tenant_id,
        secret_key=settings.secret_key,
        public_app_url=settings.public_app_url,
        ticket_ttl_hours=settings.ticket_ttl_hours,
        walk_in_penalty_minutes=settings.queue_walk_in_penalty_minutes,
    )


def get_queue_service(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: UUID = Depends(get_tenant_context),
    catalog: CatalogService = Depends(get_catalog_service),
    customers: CustomerService = Depends(get_customer_service),
    bookings: BookingService = Depends(get_booking_service),
) -> QueueService:
    """Composes queue with catalog, identity and booking.

    All four share one request-scoped session, so redeeming a ticket, checking
    the queue entry in, and transitioning the linked booking either all land or
    none of them do.
    """
    return build_queue_service(
        session, tenant_id, catalog=catalog, customers=customers, bookings=bookings
    )
