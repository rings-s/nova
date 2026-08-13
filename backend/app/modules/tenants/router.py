from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session
from app.core.pagination import PageParams
from app.modules.tenants.commands import (
    CreateBranchCommand,
    CreateTenantCommand,
    handle_create_branch,
    handle_create_tenant,
)
from app.modules.tenants.dependencies import get_branch_repository, get_tenant_repository
from app.modules.tenants.models import Branch, Tenant
from app.modules.tenants.queries import (
    GetBranchQuery,
    GetTenantQuery,
    ListBranchesQuery,
    ListTenantsQuery,
    handle_get_branch,
    handle_get_tenant,
    handle_list_branches,
    handle_list_tenants,
)
from app.modules.tenants.repository import BranchRepository, TenantRepository
from app.modules.tenants.schemas import BranchCreate, BranchRead, TenantCreate, TenantRead

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreate,
    session: AsyncSession = Depends(get_db_session),
    repository: TenantRepository = Depends(get_tenant_repository),
) -> Tenant:
    settings = get_settings()
    command = CreateTenantCommand(**payload.model_dump())
    tenant = await handle_create_tenant(
        command,
        repository=repository,
        allowed_phone_country_codes=settings.allowed_phone_country_codes,
    )
    await session.commit()
    return tenant


@router.get("", response_model=list[TenantRead])
async def list_tenants(
    params: PageParams = Depends(),
    repository: TenantRepository = Depends(get_tenant_repository),
) -> list[Tenant]:
    query = ListTenantsQuery(limit=params.limit, offset=params.offset)
    return await handle_list_tenants(query, repository=repository)


@router.get("/{tenant_id}", response_model=TenantRead)
async def get_tenant(
    tenant_id: UUID,
    repository: TenantRepository = Depends(get_tenant_repository),
) -> Tenant:
    query = GetTenantQuery(tenant_id=tenant_id)
    return await handle_get_tenant(query, repository=repository)


@router.post(
    "/{tenant_id}/branches", response_model=BranchRead, status_code=status.HTTP_201_CREATED
)
async def create_branch(
    tenant_id: UUID,
    payload: BranchCreate,
    session: AsyncSession = Depends(get_db_session),
    repository: BranchRepository = Depends(get_branch_repository),
) -> Branch:
    settings = get_settings()
    command = CreateBranchCommand(tenant_id=tenant_id, **payload.model_dump())
    branch = await handle_create_branch(
        command,
        repository=repository,
        allowed_phone_country_codes=settings.allowed_phone_country_codes,
    )
    await session.commit()
    return branch


@router.get("/{tenant_id}/branches", response_model=list[BranchRead])
async def list_branches(
    tenant_id: UUID,
    params: PageParams = Depends(),
    repository: BranchRepository = Depends(get_branch_repository),
) -> list[Branch]:
    query = ListBranchesQuery(limit=params.limit, offset=params.offset)
    return await handle_list_branches(query, repository=repository)


@router.get("/{tenant_id}/branches/{branch_id}", response_model=BranchRead)
async def get_branch(
    tenant_id: UUID,
    branch_id: UUID,
    repository: BranchRepository = Depends(get_branch_repository),
) -> Branch:
    query = GetBranchQuery(branch_id=branch_id)
    return await handle_get_branch(query, repository=repository)
