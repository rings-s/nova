"""review · APPLICATION layer — rating a completed visit.

Layer rule: domain, repository, models, events. No fastapi.
Services flush, never commit — the router owns the transaction boundary.
"""

from uuid import UUID

from app.core.events import publish_event
from app.core.security import AuthorizationError, Principal, PrincipalKind
from app.modules.booking.service import BookingService
from app.modules.catalog.service import CatalogService
from app.modules.identity.service import CustomerService
from app.modules.review.domain import is_reviewable, normalize_comment, validate_rating
from app.modules.review.events import ReviewSubmitted
from app.modules.review.exceptions import AlreadyReviewedError, ReviewNotAllowedError
from app.modules.review.models import Review
from app.modules.review.repository import ReviewRepository


class ReviewService:
    def __init__(
        self,
        *,
        repository: ReviewRepository,
        bookings: BookingService,
        catalog: CatalogService,
        customers: CustomerService,
        tenant_id: UUID,
    ) -> None:
        self.repository = repository
        self.bookings = bookings
        self.catalog = catalog
        self.customers = customers
        self.tenant_id = tenant_id

    async def submit(
        self,
        *,
        principal: Principal,
        booking_id: UUID,
        rating: int,
        comment: str | None = None,
    ) -> Review:
        """Records the caller's rating of one of their completed visits.

        Only a customer rates, and only their own booking: staff could
        otherwise rate their own salon, which is exactly what a marketplace
        ranking must not allow. Ownership comes from
        `BookingService.get_for_principal`, which answers 404 for someone
        else's booking rather than confirming it exists.
        """
        if principal.kind is not PrincipalKind.CUSTOMER:
            raise AuthorizationError("Only the customer who made a booking may rate it.")

        rating = validate_rating(rating)
        comment = normalize_comment(comment)

        booking = await self.bookings.get_for_principal(booking_id, principal)
        if not is_reviewable(str(booking.status)):
            raise ReviewNotAllowedError(booking_id)
        if await self.repository.get_by_booking(booking_id) is not None:
            raise AlreadyReviewedError(booking_id)

        review = self.repository.add(
            Review(
                tenant_id=self.tenant_id,
                booking_id=booking.id,
                business_id=booking.business_id,
                location_id=booking.location_id,
                provider_id=booking.provider_id,
                customer_id=booking.customer_id,
                rating=rating,
                comment=comment,
            )
        )
        # Flushed before the totals move, so a concurrent duplicate fails on
        # `uq_reviews_booking_id` here and the rating is never counted twice.
        await self.repository.session.flush()
        await self.catalog.record_rating(booking.business_id, rating)

        await publish_event(
            self.repository.session,
            ReviewSubmitted(
                tenant_id=self.tenant_id,
                review_id=review.id,
                business_id=booking.business_id,
                booking_id=booking.id,
                provider_id=booking.provider_id,
                rating=rating,
            ),
        )
        return review

    async def list_mine(self, principal: Principal) -> list[Review]:
        """The caller's own reviews at this tenant — what they have rated.

        Empty rather than an error for someone who has never visited: that is
        an ordinary answer, and `find_for_user` never provisions a record.
        """
        customer = await self.customers.find_for_user(principal.subject_id)
        if customer is None:
            return []
        return await self.repository.list_for_customer(customer.id)

    async def list_for_business(
        self, business_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[Review]:
        """Staff view: every review of this business, comments included."""
        return await self.repository.list_for_business(business_id, limit=limit, offset=offset)
