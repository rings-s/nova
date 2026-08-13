import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import TenantMismatchError
from app.modules.tenants.models import Branch
from app.modules.tenants.repository import BranchRepository


async def test_branch_repository_cannot_read_other_tenants_branch(
    db_session: AsyncSession, tenant_factory, branch_factory
) -> None:
    tenant_a = await tenant_factory()
    tenant_b = await tenant_factory(slug="tenant-b")
    branch_a = await branch_factory(tenant_a)

    repo_scoped_to_b = BranchRepository(db_session, tenant_b.id)

    assert await repo_scoped_to_b.get(branch_a.id) is None


async def test_branch_repository_add_rejects_mismatched_tenant(
    db_session: AsyncSession, tenant_factory
) -> None:
    tenant_a = await tenant_factory()
    tenant_b = await tenant_factory(slug="tenant-b")

    repo_scoped_to_b = BranchRepository(db_session, tenant_b.id)
    rogue_branch = Branch(
        tenant_id=tenant_a.id,
        name_en="Rogue",
        name_ar="مارق",
        slug="rogue",
        phone="+966500000002",
        timezone="Asia/Riyadh",
    )

    with pytest.raises(TenantMismatchError):
        repo_scoped_to_b.add(rogue_branch)


async def test_branch_repository_list_only_returns_scoped_tenant(
    db_session: AsyncSession, tenant_factory, branch_factory
) -> None:
    tenant_a = await tenant_factory()
    tenant_b = await tenant_factory(slug="tenant-b-2")
    await branch_factory(tenant_a)
    branch_b = await branch_factory(tenant_b)

    repo_scoped_to_b = BranchRepository(db_session, tenant_b.id)
    results = await repo_scoped_to_b.list()

    assert [b.id for b in results] == [branch_b.id]
