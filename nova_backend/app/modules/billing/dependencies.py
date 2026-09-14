"""billing · DELIVERY layer — DI providers."""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_tenant_context
from app.modules.billing.repository import (
    CommissionLineRepository,
    FirstBookingRepository,
    InvoiceRepository,
    PayoutRepository,
    SubscriptionRepository,
)
from app.modules.billing.service import BillingService


def build_billing_service(session: AsyncSession, tenant_id: UUID) -> BillingService:
    """Assembles the service outside the request DI graph.

    The event handlers and the ARQ cron jobs are the callers that need this:
    a monthly close has no bearer token and no tenant in a path, so it cannot
    resolve `get_tenant_context`.
    """
    return BillingService(
        subscriptions=SubscriptionRepository(session, tenant_id),
        lines=CommissionLineRepository(session, tenant_id),
        invoices=InvoiceRepository(session, tenant_id),
        first_bookings=FirstBookingRepository(session, tenant_id),
        payouts=PayoutRepository(session, tenant_id),
        tenant_id=tenant_id,
    )


def get_billing_service(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: UUID = Depends(get_tenant_context),
) -> BillingService:
    return build_billing_service(session, tenant_id)
