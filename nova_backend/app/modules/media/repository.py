"""media · PERSISTENCE layer — queries.

Layer rule: models + `app.db`. Must not import service, router, or fastapi.

Pure-function domain style, so there is no domain<->row mapping here: the ORM
record is what callers get back, the same arrangement `catalog` uses.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select

from app.db.repository import TenantScopedRepository
from app.modules.media.domain import MediaAssetKind
from app.modules.media.models import MediaAssetRecord


class MediaAssetRepository(TenantScopedRepository[MediaAssetRecord]):
    model = MediaAssetRecord

    def _active(self, stmt: Select) -> Select:
        return stmt.where(MediaAssetRecord.is_deleted.is_(False))

    async def get(self, id: UUID, *, include_deleted: bool = False) -> MediaAssetRecord | None:
        stmt = self._scope(self._base_select().where(MediaAssetRecord.id == id))
        if not include_deleted:
            stmt = self._active(stmt)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_business(
        self,
        business_id: UUID,
        *,
        kind: MediaAssetKind | None = None,
        ready_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MediaAssetRecord]:
        stmt = self._active(
            self._scope(self._base_select().where(MediaAssetRecord.business_id == business_id))
        )
        if kind is not None:
            stmt = stmt.where(MediaAssetRecord.kind == kind)
        if ready_only:
            # A half-uploaded asset must never reach a storefront.
            stmt = stmt.where(MediaAssetRecord.is_ready.is_(True))

        stmt = stmt.order_by(MediaAssetRecord.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_stale_uploads(
        self, *, before: datetime, limit: int = 200
    ) -> list[MediaAssetRecord]:
        """Assets whose upload window closed without a completion callback.

        These are rows pointing at bytes that were never written. The worker
        soft-deletes them so they stop appearing in a business's own media
        list as permanently-loading placeholders.
        """
        stmt = self._active(
            self._scope(
                self._base_select().where(
                    MediaAssetRecord.is_ready.is_(False),
                    MediaAssetRecord.upload_expires_at < before,
                )
            )
        ).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
