"""Domain rules for the catalog module.

Pure-function style: catalog entities are records with field-level rules, not
state machines, so the ORM model is the domain object (per the decision
recorded in ADR-0002 and confirmed for this module). Contrast `booking.domain`,
which owns a real lifecycle and therefore defines its own entity.
"""

from decimal import Decimal

from app.core.exceptions import ValidationDomainError
from app.core.validators import (
    generate_slug,
    require_bilingual_text,
    validate_gcc_phone,
    validate_timezone,
)

__all__ = [
    "MAX_SERVICE_DURATION_MINUTES",
    "MIN_SERVICE_DURATION_MINUTES",
    "RATING_PRIOR_MEAN",
    "RATING_PRIOR_WEIGHT",
    "generate_slug",
    "rating_average",
    "rating_score",
    "require_bilingual_text",
    "validate_coordinates",
    "validate_gcc_phone",
    "validate_service_duration",
    "validate_service_price",
    "validate_timezone",
]

#: Ranking by raw average would put a salon with one 5-star visit above one
#: with two hundred visits averaging 4.8. Instead a business is ranked as if it
#: had also received `RATING_PRIOR_WEIGHT` ratings of `RATING_PRIOR_MEAN`: the
#: prior dominates while there is little evidence and fades as real ratings
#: accumulate (a Bayesian average). The prior sits below "good", so a new
#: salon has to earn its place rather than start near the top.
RATING_PRIOR_MEAN = 3.5
RATING_PRIOR_WEIGHT = 5


def rating_average(rating_sum: int, rating_count: int) -> float | None:
    """The plain average, for display. None when nobody has rated yet."""
    if rating_count <= 0:
        return None
    return round(rating_sum / rating_count, 2)


def rating_score(rating_sum: int, rating_count: int) -> float:
    """The confidence-weighted score the marketplace ranks by (see above).

    `PublicCatalogRepository` computes the same expression in SQL so the
    database can order and page by it; this is the reference definition, and
    the test that pins the two together lives with the catalog tests.
    """
    return (rating_sum + RATING_PRIOR_MEAN * RATING_PRIOR_WEIGHT) / (
        rating_count + RATING_PRIOR_WEIGHT
    )


# A treatment shorter than 5 minutes is a data-entry slip, and one longer than a
# working day breaks availability generation.
MIN_SERVICE_DURATION_MINUTES = 5
MAX_SERVICE_DURATION_MINUTES = 8 * 60


def validate_service_duration(duration_minutes: int) -> int:
    if duration_minutes < MIN_SERVICE_DURATION_MINUTES:
        raise ValidationDomainError(
            f"Service duration must be at least {MIN_SERVICE_DURATION_MINUTES} minutes."
        )
    if duration_minutes > MAX_SERVICE_DURATION_MINUTES:
        raise ValidationDomainError(
            f"Service duration must not exceed {MAX_SERVICE_DURATION_MINUTES} minutes."
        )
    if duration_minutes % 5 != 0:
        raise ValidationDomainError("Service duration must be a multiple of 5 minutes.")
    return duration_minutes


def validate_service_price(price: Decimal) -> Decimal:
    # NaN and Infinity are valid Decimals and would sail through the comparisons
    # below — `as_tuple().exponent` returns 'n'/'N'/'F' for them rather than an
    # int, so the decimal-places check would raise TypeError instead of
    # rejecting the price.
    if not price.is_finite():
        raise ValidationDomainError("Service price must be a finite number.")
    if price < 0:
        raise ValidationDomainError("Service price cannot be negative.")
    exponent = price.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ValidationDomainError("Service price cannot have more than 2 decimal places.")
    return price


def validate_coordinates(latitude: float | None, longitude: float | None) -> None:
    """Both or neither — a half-set coordinate pair silently breaks map search."""
    if (latitude is None) != (longitude is None):
        raise ValidationDomainError("Latitude and longitude must be provided together.")
    if latitude is not None and not -90 <= latitude <= 90:
        raise ValidationDomainError("Latitude must be between -90 and 90.")
    if longitude is not None and not -180 <= longitude <= 180:
        raise ValidationDomainError("Longitude must be between -180 and 180.")
