"""discovery · DELIVERY layer — DI providers."""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session, get_tenant_context
from app.db.session import set_discovery_scope
from app.modules.catalog.dependencies import build_public_catalog_service
from app.modules.discovery.repository import MarketplaceReferralRepository
from app.modules.discovery.service import AttributionService, DiscoveryService


async def get_discovery_service(
    session: AsyncSession = Depends(get_db_session),
) -> DiscoveryService:
    """Builds the public marketplace service and opens its RLS window.

    Note what is missing: there is no `get_tenant_context`, and therefore no
    `get_principal`. That is the whole point of the module — a customer looking
    for a salon has neither an account nor a tenant yet — and it is why this is
    the only provider in the codebase that calls `set_discovery_scope`.

    That call is not optional. RLS fails closed, so without it every listing
    query returns zero rows rather than leaking: forgetting it breaks discovery
    loudly instead of breaking isolation quietly.
    """
    settings = get_settings()
    await set_discovery_scope(session)
    return DiscoveryService(
        catalog=build_public_catalog_service(session),
        session=session,
        referral_repository_for=lambda tenant_id: MarketplaceReferralRepository.scoped_to(
            session, tenant_id
        ),
        max_availability_days=settings.discovery_max_availability_days,
        max_public_slots=settings.discovery_max_public_slots,
    )


def build_attribution_service(session: AsyncSession, tenant_id: UUID) -> AttributionService:
    """Assembles the tenant-scoped half outside the request DI graph."""
    return AttributionService(referrals=MarketplaceReferralRepository(session, tenant_id))


def get_attribution_service(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: UUID = Depends(get_tenant_context),
) -> AttributionService:
    """The half booking depends on, scoped to the booking's own tenant.

    Shares the request session with `BookingService`, so a referral marked
    consumed and the booking that consumed it commit or roll back together —
    a booking that failed to save must not leave a spent referral behind.
    """
    return build_attribution_service(session, tenant_id)
