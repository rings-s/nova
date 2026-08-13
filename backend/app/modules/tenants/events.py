"""Domain events for the tenants module.

Defined now so command handlers have a stable shape to emit later, but not yet
dispatched anywhere — there is no event bus/outbox in this scaffold. Wire these
up when a consumer exists (e.g. a WhatsApp welcome message on TenantCreated).
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class TenantCreated:
    tenant_id: UUID
    occurred_at: datetime


@dataclass(frozen=True)
class BranchCreated:
    tenant_id: UUID
    branch_id: UUID
    occurred_at: datetime
