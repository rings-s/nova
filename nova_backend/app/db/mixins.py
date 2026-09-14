import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TenantOwnedMixin:
    """Marks a model as belonging to a single tenant.

    Any repository for a model using this mixin should extend
    `TenantScopedRepository` (see app/db/repository.py) rather than `BaseRepository`,
    so every query is filtered by tenant_id at the persistence layer.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )


class SoftDeleteMixin:
    """Retires a row without deleting it, per docs/08 section 1.

    Catalog rows are referenced by historical bookings — hard-deleting a service
    a salon stopped offering would orphan every past booking that used it. The
    row stays; `is_deleted` takes it out of listings.

    Repositories do NOT filter on this automatically. Callers that list
    catalog rows for customers must exclude deleted ones explicitly, while
    callers resolving a historical booking must still be able to read them.
    """

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def mark_deleted(self, *, now: datetime) -> None:
        self.is_deleted = True
        self.deleted_at = now
