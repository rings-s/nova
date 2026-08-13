from dataclasses import dataclass
from uuid import UUID

from app.modules.tenants.exceptions import BranchNotFoundError, TenantNotFoundError
from app.modules.tenants.models import Branch, Tenant
from app.modules.tenants.repository import BranchRepository, TenantRepository


@dataclass(frozen=True)
class GetTenantQuery:
    tenant_id: UUID


async def handle_get_tenant(query: GetTenantQuery, *, repository: TenantRepository) -> Tenant:
    tenant = await repository.get(query.tenant_id)
    if tenant is None:
        raise TenantNotFoundError(query.tenant_id)
    return tenant


@dataclass(frozen=True)
class ListTenantsQuery:
    limit: int = 20
    offset: int = 0


async def handle_list_tenants(
    query: ListTenantsQuery, *, repository: TenantRepository
) -> list[Tenant]:
    return await repository.list(limit=query.limit, offset=query.offset)


@dataclass(frozen=True)
class GetBranchQuery:
    branch_id: UUID


async def handle_get_branch(query: GetBranchQuery, *, repository: BranchRepository) -> Branch:
    branch = await repository.get(query.branch_id)
    if branch is None:
        raise BranchNotFoundError(query.branch_id)
    return branch


@dataclass(frozen=True)
class ListBranchesQuery:
    limit: int = 20
    offset: int = 0


async def handle_list_branches(
    query: ListBranchesQuery, *, repository: BranchRepository
) -> list[Branch]:
    return await repository.list(limit=query.limit, offset=query.offset)
