"""notification · DELIVERY layer — HTTP.

Layer rule: schemas, service, dependencies. No business rules here.

Note there is no "send a message" endpoint, and there should not be one. This
context reacts to domain events; an endpoint that let staff (or an AI agent)
send arbitrary messages would bypass the consent and quiet-hours gates that are
the whole reason the module exists.
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.pagination import PageParams
from app.core.schemas import Page
from app.core.security import require_staff
from app.modules.notification.dependencies import get_notification_service
from app.modules.notification.schemas import NotificationOut
from app.modules.notification.service import NotificationService

router = APIRouter(prefix="/tenants/{tenant_id}/notifications", tags=["notification"])


@router.get("", response_model=Page[NotificationOut], dependencies=[Depends(require_staff)])
async def list_customer_notifications(
    tenant_id: UUID,
    customer_id: UUID,
    params: PageParams = Depends(),
    service: NotificationService = Depends(get_notification_service),
) -> Page[NotificationOut]:
    """The delivery log for one customer — "did they actually get told?"."""
    rows = await service.list_for_customer(customer_id, limit=params.limit, offset=params.offset)
    return Page(items=[NotificationOut.model_validate(r) for r in rows])
