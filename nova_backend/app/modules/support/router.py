"""support · DELIVERY layer — HTTP.

Layer rule: schemas, service, dependencies. No business rules here.

Every route needs `view_customers`: a follow-up holds a customer's name,
number and own words, like the customer book and the call log.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.pagination import PageParams
from app.core.schemas import Page
from app.core.security import Principal, get_principal
from app.core.throttling import write_rate_limit
from app.modules.identity.dependencies import RequirePermission
from app.modules.identity.domain import StaffPermission
from app.modules.support.dependencies import get_support_service
from app.modules.support.domain import FollowUpStatus
from app.modules.support.schemas import FollowUpCountOut, FollowUpOut
from app.modules.support.service import SupportService

router = APIRouter(
    prefix="/tenants/{tenant_id}/follow-ups",
    tags=["support"],
    dependencies=[Depends(RequirePermission(StaffPermission.VIEW_CUSTOMERS))],
)


@router.get("", response_model=Page[FollowUpOut])
async def list_follow_ups(
    tenant_id: UUID,
    *,
    status: Annotated[
        FollowUpStatus | None,
        Query(description="Only open or only resolved ones; both when left out."),
    ] = None,
    params: Annotated[PageParams, Depends()],
    service: Annotated[SupportService, Depends(get_support_service)],
) -> Page[FollowUpOut]:
    """Customers an AI agent promised a person would get back to, newest first.

    Opened by the chat assistants and by Sara on the phone when they hand off,
    with who to contact, the agent's summary and the customer's own last words.
    """
    rows = await service.list(status=status, limit=params.limit, offset=params.offset)
    return Page(items=[FollowUpOut.model_validate(row) for row in rows])


@router.get("/count", response_model=FollowUpCountOut)
async def count_follow_ups(
    tenant_id: UUID,
    service: Annotated[SupportService, Depends(get_support_service)],
) -> FollowUpCountOut:
    """How many follow-ups are still open, for the dashboard's badge."""
    return FollowUpCountOut(open=await service.count_open())


@router.post(
    "/{follow_up_id}/resolve",
    response_model=FollowUpOut,
    dependencies=[Depends(write_rate_limit)],
)
async def resolve_follow_up(
    tenant_id: UUID,
    follow_up_id: UUID,
    principal: Annotated[Principal, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[SupportService, Depends(get_support_service)],
) -> FollowUpOut:
    """Mark a follow-up done once someone has got back to the customer.

    Resolving one already resolved changes nothing. It reopens by itself if
    the same conversation or call hands off again.
    """
    follow_up = await service.resolve(follow_up_id, principal)
    await session.commit()
    return FollowUpOut.model_validate(follow_up)
