from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session, get_tenant_context
from app.integrations.storage import ImageStore, LocalImageStore
from app.modules.catalog.repository import (
    BusinessPhotoRepository,
    BusinessRepository,
    LocationRepository,
    ProviderRepository,
    PublicCatalogRepository,
    ServiceRepository,
)
from app.modules.catalog.service import CatalogService, PublicCatalogService


def get_image_store() -> ImageStore:
    """Where business photos live. Local disk today; see `integrations.storage`."""
    return LocalImageStore(get_settings().media_root)


def build_catalog_service(session: AsyncSession, tenant_id: UUID) -> CatalogService:
    """Assembles the service from a session and a tenant, with no FastAPI involved.

    Separate from the `Depends` provider below so code outside the request DI
    graph — the payment webhook, the outbox dispatcher — can build the same
    service without an authenticated tenant context. Duplicating this wiring in
    those places is how two constructions of "the same" service silently drift
    apart.
    """
    settings = get_settings()
    return CatalogService(
        businesses=BusinessRepository(session, tenant_id),
        locations=LocationRepository(session, tenant_id),
        services=ServiceRepository(session, tenant_id),
        providers=ProviderRepository(session, tenant_id),
        tenant_id=tenant_id,
        allowed_phone_country_codes=settings.allowed_phone_country_codes,
        photos=BusinessPhotoRepository(session, tenant_id),
        images=get_image_store(),
    )


def get_catalog_service(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: UUID = Depends(get_tenant_context),
) -> CatalogService:
    """Builds every catalog repository against one session and one tenant.

    `tenant_id` comes from the URL path via `get_tenant_context` — never from
    the body or a query param (ADR-0003).
    """
    return build_catalog_service(session, tenant_id)


def build_public_catalog_service(session: AsyncSession) -> PublicCatalogService:
    """Catalog's read-only, cross-tenant half. No tenant, by design.

    Lives here rather than in `discovery`, which is its only consumer, because
    building it means naming `PublicCatalogRepository` — and a module reaching
    into another module's repository is the boundary violation
    `tests/test_architecture.py` exists to catch. Catalog owns these tables, so
    catalog hands out the assembled service and discovery never sees the
    repository at all.

    The caller must open the RLS window first (`set_discovery_scope`), or every
    method on the returned service correctly finds nothing.
    """
    return PublicCatalogService(listings=PublicCatalogRepository(session), images=get_image_store())
