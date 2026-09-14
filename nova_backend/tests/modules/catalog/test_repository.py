"""Persistence and tenant-isolation tests for catalog.

These are the ADR-0003 tests. They are the reason `TenantScopedRepository`
exists and they must never be allowed to regress — a failure here is a
cross-tenant data leak, the most severe defect this system can have.

They read as the schema owner, which row-level security does not restrict, so
the repository's own filter is the only thing that can pass them. As `nova_app`,
RLS would hide the other tenant's rows first and a broken filter would pass
unnoticed; RLS is tested on its own in tests/test_row_level_security.py.

Moved here from the old tenants module when `Branch` became `catalog.Location`.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import TenantMismatchError
from app.modules.catalog.models import Location
from app.modules.catalog.repository import LocationRepository


async def test_repository_cannot_read_another_tenants_row(
    db_session: AsyncSession, tenant_factory, business_factory, location_factory, as_owner
) -> None:
    tenant_a = await tenant_factory()
    tenant_b = await tenant_factory()
    business_a = await business_factory(tenant_a)
    location_a = await location_factory(business_a)

    repo_scoped_to_b = LocationRepository(db_session, tenant_b.id)

    async with as_owner():
        assert await repo_scoped_to_b.get(location_a.id) is None


async def test_repository_add_rejects_mismatched_tenant(
    db_session: AsyncSession, tenant_factory, business_factory
) -> None:
    tenant_a = await tenant_factory()
    tenant_b = await tenant_factory()
    business_a = await business_factory(tenant_a)

    repo_scoped_to_b = LocationRepository(db_session, tenant_b.id)
    rogue = Location(
        tenant_id=tenant_a.id,
        business_id=business_a.id,
        name_en="Rogue Branch",
        name_ar="فرع مخالف",
        slug="rogue-branch",
        phone="+966500000009",
        timezone="Asia/Riyadh",
    )

    with pytest.raises(TenantMismatchError):
        repo_scoped_to_b.add(rogue)


async def test_list_only_returns_scoped_tenant(
    db_session: AsyncSession, tenant_factory, business_factory, location_factory, as_owner
) -> None:
    tenant_a = await tenant_factory()
    tenant_b = await tenant_factory()
    business_a = await business_factory(tenant_a)
    business_b = await business_factory(tenant_b)
    await location_factory(business_a)
    location_b = await location_factory(business_b)

    repo_scoped_to_b = LocationRepository(db_session, tenant_b.id)
    async with as_owner():
        results = await repo_scoped_to_b.list()

    assert [loc.id for loc in results] == [location_b.id]


async def test_soft_deleted_rows_are_hidden_by_default(
    db_session: AsyncSession, tenant_factory, business_factory, location_factory, as_owner
) -> None:
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    location = await location_factory(business)
    repo = LocationRepository(db_session, tenant.id)

    async with as_owner():
        location.mark_deleted(now=datetime.now(UTC))
        await db_session.flush()

        assert await repo.get(location.id) is None
        # ...but history can still resolve it, which is why the switch exists.
        assert await repo.get(location.id, include_deleted=True) is not None
