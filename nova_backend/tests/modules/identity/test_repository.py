"""Persistence tests for identity.

`Tenant` is the isolation root itself, so `TenantRepository` extends the
unscoped `BaseRepository`. The cross-tenant isolation tests that matter live
in `tests/modules/catalog/test_repository.py`, against a tenant-owned model.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.repository import TenantRepository


async def test_get_by_slug_finds_tenant(db_session: AsyncSession, tenant_factory) -> None:
    tenant = await tenant_factory(slug="glow-salon")
    repo = TenantRepository(db_session)

    found = await repo.get_by_slug("glow-salon")

    assert found is not None
    assert found.id == tenant.id


async def test_get_by_slug_returns_none_when_missing(db_session: AsyncSession) -> None:
    repo = TenantRepository(db_session)
    assert await repo.get_by_slug("does-not-exist") is None
