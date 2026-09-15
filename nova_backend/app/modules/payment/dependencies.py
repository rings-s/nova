"""payment · DELIVERY layer — DI providers."""

from decimal import Decimal
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session, get_tenant_context
from app.core.security import AuthorizationError, Principal
from app.integrations.payments.moyasar import PaymentGateway, build_payment_gateway
from app.modules.booking.dependencies import build_booking_service, get_booking_service
from app.modules.booking.service import BookingService
from app.modules.payment.repository import PaymentRepository, WebhookEventRepository
from app.modules.payment.service import PaymentService, PaymentWebhookProcessor


def get_payment_gateway() -> PaymentGateway:
    """The live adapter when credentials exist, otherwise the placeholder.

    Resolved per request rather than at import time so a deployment can add
    credentials and restart without any code change.
    """
    settings = get_settings()
    return build_payment_gateway(
        api_key=settings.moyasar_api_key,
        webhook_secret=settings.moyasar_webhook_secret,
        base_url=settings.moyasar_base_url,
    )


def build_payment_service(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    gateway: PaymentGateway | None = None,
    bookings: BookingService | None = None,
) -> PaymentService:
    """Assembles the service outside the request DI graph.

    The webhook handler is the caller that needs this: it discovers its tenant
    from the payment rather than from an authenticated path, so it cannot
    resolve `get_tenant_context` and cannot use the provider below.
    """
    settings = get_settings()
    return PaymentService(
        repository=PaymentRepository(session, tenant_id),
        gateway=gateway or get_payment_gateway(),
        bookings=bookings or build_booking_service(session, tenant_id),
        tenant_id=tenant_id,
        public_app_url=settings.public_app_url,
        default_deposit_percent=settings.default_deposit_percent,
    )


def get_payment_service(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: UUID = Depends(get_tenant_context),
    gateway: PaymentGateway = Depends(get_payment_gateway),
    bookings: BookingService = Depends(get_booking_service),
) -> PaymentService:
    return build_payment_service(session, tenant_id, gateway=gateway, bookings=bookings)


def get_webhook_processor(
    session: AsyncSession = Depends(get_db_session),
    gateway: PaymentGateway = Depends(get_payment_gateway),
) -> PaymentWebhookProcessor:
    """Deliberately has no `get_tenant_context` dependency.

    A webhook has no bearer token and no tenant in its path — it authenticates
    by signature alone, and the tenant is discovered from the payment it
    references. Wiring `get_tenant_context` here would make the endpoint
    require the authentication the gateway cannot provide.
    """
    return PaymentWebhookProcessor(events=WebhookEventRepository(session), gateway=gateway)


def refuse_customer_amount(
    *, amount: Decimal | None, currency: str | None, principal: Principal
) -> None:
    """Only staff may name what a payment charges.

    Left unset, the amount is the booking's own price under the tenant's deposit
    policy. A customer able to set it could pay 1 SAR for a 150 SAR booking and
    have it confirmed. A customer who sends either field is refused rather than
    quietly charged the right amount: a client that sends them has a bug worth
    seeing.
    """
    if (amount is not None or currency is not None) and not principal.is_staff:
        raise AuthorizationError("Only staff may set a payment's amount or currency.")
