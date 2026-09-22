"""review · DOMAIN layer — what makes a rating acceptable.

Pure-function style: a review is written once and never transitions, so the
ORM model is the domain object and these are its field rules.
"""

from app.core.exceptions import ValidationDomainError

MIN_RATING = 1
MAX_RATING = 5
MAX_COMMENT_LENGTH = 1000

#: The only booking status a review may be attached to. A cancelled booking or
#: a no-show was not a visit, and a confirmed one has not happened yet.
REVIEWABLE_STATUS = "completed"


def validate_rating(rating: int) -> int:
    # `bool` is an `int` in Python; `True` is not a rating of 1.
    if isinstance(rating, bool) or not MIN_RATING <= rating <= MAX_RATING:
        raise ValidationDomainError(
            f"A rating is a whole number from {MIN_RATING} to {MAX_RATING}."
        )
    return rating


def normalize_comment(comment: str | None) -> str | None:
    """Trimmed text, or None for nothing worth keeping."""
    if comment is None:
        return None
    comment = comment.strip()
    if not comment:
        return None
    if len(comment) > MAX_COMMENT_LENGTH:
        raise ValidationDomainError(f"A comment is at most {MAX_COMMENT_LENGTH} characters.")
    return comment


def is_reviewable(booking_status: str) -> bool:
    return booking_status == REVIEWABLE_STATUS
