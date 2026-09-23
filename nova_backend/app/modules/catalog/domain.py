"""Domain rules for the catalog module.

Pure-function style: catalog entities are records with field-level rules, not
state machines, so the ORM model is the domain object (per the decision
recorded in ADR-0002 and confirmed for this module). Contrast `booking.domain`,
which owns a real lifecycle and therefore defines its own entity.
"""

import hashlib
import hmac
from decimal import Decimal

from app.core.exceptions import ValidationDomainError
from app.core.validators import (
    generate_slug,
    require_bilingual_text,
    validate_gcc_phone,
    validate_timezone,
)

__all__ = [
    "MAX_GALLERY_PHOTOS",
    "MAX_SERVICE_DURATION_MINUTES",
    "MIN_SERVICE_DURATION_MINUTES",
    "PHOTO_KINDS",
    "PHOTO_LINK_PURPOSE",
    "PHOTO_LINK_TTL_SECONDS",
    "PHOTO_VARIANTS",
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

#: A cover plus this many gallery photos per business. Enough to show the
#: place; few enough that a storefront loads quickly on a phone.
MAX_GALLERY_PHOTOS = 12
PHOTO_KINDS = frozenset({"cover", "gallery"})
#: Stored sizes, matching `integrations.images.VARIANT_SIZES`.
PHOTO_VARIANTS = frozenset({"large", "thumb"})


def validate_photo_kind(kind: str) -> str:
    if kind not in PHOTO_KINDS:
        raise ValidationDomainError("A photo is either the cover or part of the gallery.")
    return kind


def photo_storage_key(storage_prefix: str, variant: str) -> str:
    if variant not in PHOTO_VARIANTS:
        raise ValidationDomainError("Unknown photo size.")
    return f"{storage_prefix}/{variant}.webp"


#: How long a signed photo link works. Long enough for a dashboard session to
#: keep showing its previews, short enough that a copied link goes stale.
PHOTO_LINK_TTL_SECONDS = 60 * 60
#: `security.purpose_key` purpose for photo links: a signature minted for this
#: can't be mistaken for any other kind of token, nor forge one.
PHOTO_LINK_PURPOSE = "photo_link"


def sign_photo_link(*, photo_id: str, tenant_id: str, expires: int, key: str) -> str:
    """HMAC over what the link grants: this photo, in this tenant, until then."""
    message = f"{photo_id}:{tenant_id}:{expires}".encode()
    return hmac.new(key.encode(), message, hashlib.sha256).hexdigest()


def photo_link_valid(
    *, photo_id: str, tenant_id: str, expires: int, signature: str, key: str, now: int
) -> bool:
    if expires < now:
        return False
    expected = sign_photo_link(photo_id=photo_id, tenant_id=tenant_id, expires=expires, key=key)
    return hmac.compare_digest(expected, signature)


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
