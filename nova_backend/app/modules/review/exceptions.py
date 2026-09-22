"""review · DOMAIN layer — module errors."""

from uuid import UUID

from app.core.exceptions import ConflictError


class ReviewNotAllowedError(ConflictError):
    """The booking exists and is the caller's, but is not a completed visit."""

    code = "review_not_allowed"

    def __init__(self, booking_id: UUID) -> None:
        super().__init__(f"Booking {booking_id} can be rated once the visit is completed.")


class AlreadyReviewedError(ConflictError):
    code = "already_reviewed"

    def __init__(self, booking_id: UUID) -> None:
        super().__init__(f"Booking {booking_id} has already been rated.")
