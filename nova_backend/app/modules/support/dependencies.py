"""support · DELIVERY layer — DI providers."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_tenant_context
from app.modules.identity.dependencies import build_customer_service
from app.modules.identity.service import CustomerService
from app.modules.support.repository import FollowUpRepository
from app.modules.support.service import SupportService


def build_support_service(
    session: AsyncSession, tenant_id: UUID, *, customers: CustomerService | None = None
) -> SupportService:
    """Assembles the service outside the request DI graph (agents, call center)."""
    return SupportService(
        repository=FollowUpRepository(session, tenant_id),
        customers=customers or build_customer_service(session, tenant_id),
        tenant_id=tenant_id,
    )


def get_support_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tenant_id: Annotated[UUID, Depends(get_tenant_context)],
) -> SupportService:
    return build_support_service(session, tenant_id)
