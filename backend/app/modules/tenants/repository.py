from app.db.repository import BaseRepository, TenantScopedRepository
from app.modules.tenants.models import Branch, Tenant


class TenantRepository(BaseRepository[Tenant]):
    model = Tenant

    async def get_by_slug(self, slug: str) -> Tenant | None:
        stmt = self._base_select().where(Tenant.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class BranchRepository(TenantScopedRepository[Branch]):
    model = Branch

    async def get_by_slug(self, slug: str) -> Branch | None:
        stmt = self._scope(self._base_select().where(Branch.slug == slug))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
