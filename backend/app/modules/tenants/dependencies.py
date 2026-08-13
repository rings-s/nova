from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_tenant_context
from app.modules.tenants.repository import BranchRepository, TenantRepository


def get_tenant_repository(
    session: AsyncSession = Depends(get_db_session),
) -> TenantRepository:
    return TenantRepository(session)


def get_branch_repository(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: UUID = Depends(get_tenant_context),
) -> BranchRepository:
    return BranchRepository(session, tenant_id)
