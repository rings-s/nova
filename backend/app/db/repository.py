from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError

ModelT = TypeVar("ModelT")


class TenantMismatchError(ConflictError):
    code = "tenant_mismatch"

    def __init__(self, entity_tenant_id: UUID, scope_tenant_id: UUID) -> None:
        super().__init__(
            f"Entity belongs to tenant {entity_tenant_id}, not scoped tenant {scope_tenant_id}."
        )


class BaseRepository(Generic[ModelT]):
    """Persistence for models that are not tenant-owned (e.g. Tenant itself)."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base_select(self) -> Select:
        return select(self.model)

    async def get(self, id: UUID) -> ModelT | None:
        return await self.session.get(self.model, id)

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        return entity

    async def list(self, *, limit: int = 20, offset: int = 0) -> list[ModelT]:
        stmt = self._base_select().limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class TenantScopedRepository(BaseRepository[ModelT]):
    """Repository base for models carrying `tenant_id` (see `TenantOwnedMixin`).

    Every read goes through `_scope`, which adds a `tenant_id == self.tenant_id`
    filter, so a repository instance scoped to one tenant structurally cannot
    read or write another tenant's rows — there is no unscoped query method to
    reach for by mistake. `tenant_id` is fixed at construction time by the
    FastAPI dependency that builds the repository from the URL path, never from
    a query parameter or request body.

    This is an application-layer control, not a database-layer one; it does not
    protect against raw SQL or a future module bypassing this base class. See
    docs/decisions/0003-tenant-isolation-strategy.md for the tradeoff and the
    Postgres Row-Level Security hardening noted there as future work.
    """

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        super().__init__(session)
        self.tenant_id = tenant_id

    def _scope(self, stmt: Select) -> Select:
        return stmt.where(self.model.tenant_id == self.tenant_id)

    async def get(self, id: UUID) -> ModelT | None:
        stmt = self._scope(self._base_select().where(self.model.id == id))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, entity: ModelT) -> ModelT:
        entity_tenant_id = entity.tenant_id
        if entity_tenant_id != self.tenant_id:
            raise TenantMismatchError(entity_tenant_id, self.tenant_id)
        self.session.add(entity)
        return entity

    async def list(self, *, limit: int = 20, offset: int = 0) -> list[ModelT]:
        stmt = self._scope(self._base_select()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
