"""review · DELIVERY layer — DI providers."""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_tenant_context
from app.modules.booking.dependencies import build_booking_service, get_booking_service
from app.modules.booking.service import BookingService
from app.modules.catalog.dependencies import build_catalog_service, get_catalog_service
from app.modules.catalog.service import CatalogService
from app.modules.identity.dependencies import build_customer_service, get_customer_service
from app.modules.identity.service import CustomerService
from app.modules.review.repository import ReviewRepository
from app.modules.review.service import ReviewService


def build_review_service(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    bookings: BookingService | None = None,
    catalog: CatalogService | None = None,
    customers: CustomerService | None = None,
) -> ReviewService:
    """Assembles the service outside the request DI graph (worker, agents)."""
    catalog = catalog or build_catalog_service(session, tenant_id)
    customers = customers or build_customer_service(session, tenant_id)
    return ReviewService(
        repository=ReviewRepository(session, tenant_id),
        bookings=bookings
        or build_booking_service(session, tenant_id, catalog=catalog, customers=customers),
        catalog=catalog,
        customers=customers,
        tenant_id=tenant_id,
    )


def get_review_service(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: UUID = Depends(get_tenant_context),
    bookings: BookingService = Depends(get_booking_service),
    catalog: CatalogService = Depends(get_catalog_service),
    customers: CustomerService = Depends(get_customer_service),
) -> ReviewService:
    return build_review_service(
        session, tenant_id, bookings=bookings, catalog=catalog, customers=customers
    )
