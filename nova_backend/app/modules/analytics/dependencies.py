"""analytics · DELIVERY layer — DI providers."""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session, get_tenant_context
from app.modules.analytics.service import AnalyticsService
from app.modules.billing.dependencies import build_billing_service, get_billing_service
from app.modules.billing.service import BillingService
from app.modules.booking.dependencies import build_booking_service, get_booking_service
from app.modules.booking.service import BookingService
from app.modules.catalog.dependencies import build_catalog_service, get_catalog_service
from app.modules.catalog.service import CatalogService
from app.modules.payment.dependencies import build_payment_service, get_payment_service
from app.modules.payment.service import PaymentService
from app.modules.queue.dependencies import build_queue_service, get_queue_service
from app.modules.queue.service import QueueService


def build_analytics_service(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    catalog: CatalogService | None = None,
    bookings: BookingService | None = None,
    payments: PaymentService | None = None,
    queues: QueueService | None = None,
    billing: BillingService | None = None,
) -> AnalyticsService:
    """Assembles the service outside the request DI graph.

    Every collaborator is another module's service, built by that module's own
    factory: analytics never names a repository (tests/test_architecture.py).
    """
    settings = get_settings()
    catalog = catalog or build_catalog_service(session, tenant_id)
    bookings = bookings or build_booking_service(session, tenant_id, catalog=catalog)
    return AnalyticsService(
        tenant_id=tenant_id,
        catalog=catalog,
        bookings=bookings,
        payments=payments or build_payment_service(session, tenant_id, bookings=bookings),
        queues=queues
        or build_queue_service(session, tenant_id, catalog=catalog, bookings=bookings),
        billing=billing or build_billing_service(session, tenant_id),
        default_currency=settings.default_currency,
        default_timezone=settings.default_timezone,
    )


def get_analytics_service(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: UUID = Depends(get_tenant_context),
    catalog: CatalogService = Depends(get_catalog_service),
    bookings: BookingService = Depends(get_booking_service),
    payments: PaymentService = Depends(get_payment_service),
    queues: QueueService = Depends(get_queue_service),
    billing: BillingService = Depends(get_billing_service),
) -> AnalyticsService:
    """Tenant-scoped through `get_tenant_context`, like every other module."""
    return build_analytics_service(
        session,
        tenant_id,
        catalog=catalog,
        bookings=bookings,
        payments=payments,
        queues=queues,
        billing=billing,
    )
