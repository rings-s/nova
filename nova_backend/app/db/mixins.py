import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    # `updated_at` is computed by the database on every UPDATE. Without
    # `eager_defaults`, SQLAlchemy does not read that value back at flush — it
    # *expires* the attribute instead, to be lazy-loaded on next access. Under
    # an async session that next access is the router serialising the response
    # after commit, outside the greenlet the load needs, and it raises
    # MissingGreenlet: a 500 from every endpoint that changes a row and returns
    # it (catalog listing toggle, customer consent, membership role and
    # revocation). With it, the UPDATE carries RETURNING and the fresh value is
    # already in memory. Set here because this mixin is where `onupdate` lives;
    # no model declares its own `__mapper_args__`, and one that does must keep
    # this key or reintroduce the bug.
    __mapper_args__ = {"eager_defaults": True}

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
