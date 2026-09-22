"""review · DELIVERY layer — HTTP.

Layer rule: schemas, service, dependencies. No business rules here.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.pagination import PageParams
from app.core.schemas import Page
from app.core.security import Principal, get_principal, require_staff
from app.core.throttling import write_rate_limit
from app.modules.review.dependencies import get_review_service
from app.modules.review.schemas import MyReviewOut, ReviewOut, SubmitReviewRequest
from app.modules.review.service import ReviewService

router = APIRouter(prefix="/tenants/{tenant_id}/reviews", tags=["review"])


@router.post(
    "",
    response_model=MyReviewOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(write_rate_limit)],
)
async def submit_review(
    tenant_id: UUID,
    payload: SubmitReviewRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db_session),
    service: ReviewService = Depends(get_review_service),
) -> object:
    """Rate one of your own completed visits, once."""
    review = await service.submit(
        principal=principal,
        booking_id=payload.booking_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    await session.commit()
    return review


@router.get("/mine", response_model=list[MyReviewOut])
async def list_my_reviews(
    tenant_id: UUID,
    principal: Principal = Depends(get_principal),
    service: ReviewService = Depends(get_review_service),
) -> object:
    """Your reviews at this business — which of your visits you have rated."""
    return await service.list_mine(principal)


@router.get("", response_model=Page[ReviewOut], dependencies=[Depends(require_staff)])
async def list_business_reviews(
    tenant_id: UUID,
    business_id: UUID,
    params: PageParams = Depends(),
    service: ReviewService = Depends(get_review_service),
) -> Page[ReviewOut]:
    """Every review of one business, comments included. Staff only."""
    rows = await service.list_for_business(business_id, limit=params.limit, offset=params.offset)
    return Page(items=[ReviewOut.model_validate(row) for row in rows])
