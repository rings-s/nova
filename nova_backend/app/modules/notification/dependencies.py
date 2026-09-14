"""notification · DELIVERY layer — DI providers."""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session, get_tenant_context
from app.integrations.whatsapp.client import WhatsAppClient, build_whatsapp_client
from app.modules.identity.dependencies import (
    build_customer_service,
    get_customer_service,
)
from app.modules.identity.service import CustomerService
from app.modules.notification.repository import NotificationRepository
from app.modules.notification.service import NotificationService


def get_whatsapp_client() -> WhatsAppClient:
    settings = get_settings()
    return build_whatsapp_client(
        api_key=settings.whatsapp_bsp_api_key,
        phone_number_id=settings.whatsapp_phone_number_id,
        base_url=settings.whatsapp_bsp_base_url,
    )


def build_notification_service(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    whatsapp: WhatsAppClient | None = None,
    customers: CustomerService | None = None,
) -> NotificationService:
    """Assembles the service outside the request DI graph.

    The outbox dispatcher is the main caller — it reacts to events in a worker
    process with no HTTP request and no authenticated tenant context.
    """
    settings = get_settings()
    return NotificationService(
        repository=NotificationRepository(session, tenant_id),
        whatsapp=whatsapp or get_whatsapp_client(),
        customers=customers or build_customer_service(session, tenant_id),
        tenant_id=tenant_id,
        default_timezone=settings.default_timezone,
        quiet_hours_start=settings.quiet_hours_start,
        quiet_hours_end=settings.quiet_hours_end,
    )


def get_notification_service(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: UUID = Depends(get_tenant_context),
    whatsapp: WhatsAppClient = Depends(get_whatsapp_client),
    customers: CustomerService = Depends(get_customer_service),
) -> NotificationService:
    return build_notification_service(session, tenant_id, whatsapp=whatsapp, customers=customers)
