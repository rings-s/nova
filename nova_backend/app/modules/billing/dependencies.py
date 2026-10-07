"""billing · DELIVERY layer — DI providers."""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session, get_tenant_context
from app.integrations.payments.moyasar import PaymentGateway
from app.modules.billing.repository import (
    CommissionLineRepository,
    FirstBookingRepository,
    InvoiceRepository,
    PayoutRepository,
    SubscriptionCheckoutRepository,
    SubscriptionRepository,
    UnscopedCheckoutRepository,
    UnscopedInvoiceRepository,
)
from app.modules.billing.service import BillingService, BillingSweeper
from app.modules.payment.dependencies import get_payment_gateway


def build_billing_service(
    session: AsyncSession, tenant_id: UUID, *, gateway: PaymentGateway | None = None
) -> BillingService:
    """Assembles the service outside the request DI graph.

    The event handlers and the ARQ cron jobs are the callers that need this:
    a monthly close has no bearer token and no tenant in a path, so it cannot
    resolve `get_tenant_context`.
    """
    settings = get_settings()
    return BillingService(
        subscriptions=SubscriptionRepository(session, tenant_id),
        lines=CommissionLineRepository(session, tenant_id),
        invoices=InvoiceRepository(session, tenant_id),
        first_bookings=FirstBookingRepository(session, tenant_id),
        payouts=PayoutRepository(session, tenant_id),
        tenant_id=tenant_id,
        checkouts=SubscriptionCheckoutRepository(session, tenant_id),
        # Moyasar is the same account the salons' deposits go through; the
        # checkout's metadata (`purpose: subscription`) tells them apart.
        gateway=gateway or get_payment_gateway(),
        public_app_url=settings.public_app_url,
        checkout_ttl_minutes=settings.moyasar_checkout_ttl_minutes,
    )


def get_billing_service(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: UUID = Depends(get_tenant_context),
    gateway: PaymentGateway = Depends(get_payment_gateway),
) -> BillingService:
    return build_billing_service(session, tenant_id, gateway=gateway)


async def subscription_checkout_tenant(
    session: AsyncSession, gateway_invoice_id: str
) -> UUID | None:
    """Which tenant opened this Moyasar invoice as a plan checkout, if any.

    For the Moyasar webhook, before any tenant is known; the caller must have
    opened `bypass_tenant_scope`.
    """
    return await UnscopedCheckoutRepository(session).tenant_of_gateway_invoice(gateway_invoice_id)


def build_billing_sweeper(session: AsyncSession) -> BillingSweeper:
    """Cross-tenant, for the worker. Call `bypass_tenant_scope` on the session first."""
    return BillingSweeper(UnscopedInvoiceRepository(session))
