"""admin · PERSISTENCE layer — the console's audit log.

Layer rule: sqlalchemy + `app.db` only. Must not import service or router.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPKMixin
from app.db.types import EnumValue
from app.modules.admin.domain import AdminAuditKind


class AdminAuditEntry(UUIDPKMixin, Base):
    """One thing a superuser looked at or did in the console.

    A platform table, not a tenant's: no `tenant_id` column, and so no RLS
    policy. The tenant a row belonged to is `target_tenant_id`, kept for the
    reader and never used for scoping. Append-only for the app role: migration
    `d2e3f4a5b6c7` revokes UPDATE and DELETE, so a superuser cannot tidy away
    their own trail through the app.
    """

    __tablename__ = "admin_audit_log"

    #: `clock_timestamp()`, not `now()`: the moment of the read itself, which
    #: orders several entries made in one transaction.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
    #: The account behind the token; a service principal has none to name.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[AdminAuditKind] = mapped_column(
        EnumValue(AdminAuditKind, length=16), nullable=False
    )
    table_name: Mapped[str] = mapped_column(String(64), nullable=False)
    row_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    #: The search, filters and page of a list; the reason given for an action.
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_admin_audit_log_occurred_at", "occurred_at"),
        Index("ix_admin_audit_log_actor_id", "actor_id"),
    )
