"""discovery · DOMAIN layer — the rules.

Layer rule: stdlib, pydantic, and `app.core` values/exceptions only.
Must not import fastapi or sqlalchemy. Nothing here knows a database exists.

Pure-function style (see nova_backend/README.md, "Two styles of domain.py").
A referral has no lifecycle to protect — it is created once, read once, and
expires — so there is no rich entity here, only the arithmetic and the
validation that decides what a referral means.
"""

import hashlib
import math
import secrets
from datetime import UTC, datetime, timedelta

from app.core.exceptions import ValidationDomainError

#: How long a marketplace click keeps attributing bookings to NOVA.
#: docs/11 section 3 rule 4: "a marketplace click attributes for 30 days. A
#: booking outside the window with no prior marketplace touch is direct."
REFERRAL_WINDOW_DAYS = 30

#: Bytes of entropy in a referral token. 32 bytes is the same strength the
#: queue module gives a ticket token, and for a related reason: possession of
#: this string is what makes a booking billable, so it must not be guessable.
_REFERRAL_TOKEN_BYTES = 32

#: Kilometres. Mean Earth radius, which is the right constant for a
#: great-circle distance on a sphere.
_EARTH_RADIUS_KM = 6371.0088

#: Widest radius a single search may ask for. Without a cap, `radius_km=40000`
#: is a full table scan dressed up as a location filter.
MAX_SEARCH_RADIUS_KM = 100.0

#: Shortest search term worth running. One or two characters match most of the
#: table and cost a scan to prove it.
MIN_SEARCH_TERM_LENGTH = 2


def normalize_search_term(term: str | None) -> str | None:
    """Trims a search box into something worth querying, or nothing.

    Returns None for anything too short to narrow the result set, so the caller
    treats it as "no term given" and lists rather than searches. Raising here
    instead would turn a customer backspacing over their query into an error.

    The `%` and `_` escaping matters: they are ILIKE wildcards, so a customer
    searching for a literal "50% off" would otherwise match every row.
    """
    if term is None:
        return None
    cleaned = term.strip()
    if len(cleaned) < MIN_SEARCH_TERM_LENGTH:
        return None
    return cleaned.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def validate_radius_km(radius_km: float) -> float:
    if radius_km <= 0:
        raise ValidationDomainError("radius_km must be greater than zero.")
    if radius_km > MAX_SEARCH_RADIUS_KM:
        raise ValidationDomainError(f"radius_km may not exceed {MAX_SEARCH_RADIUS_KM}.")
    return radius_km


def validate_coordinate_pair(latitude: float | None, longitude: float | None) -> None:
    """Both or neither, and each in range.

    A half-set pair is the failure `catalog.domain.validate_coordinates` warns
    about, seen from the query side: a search with a latitude and no longitude
    silently becomes a search of the whole country.
    """
    if (latitude is None) != (longitude is None):
        raise ValidationDomainError("latitude and longitude must be given together.")
    if latitude is not None and not -90 <= latitude <= 90:
        raise ValidationDomainError("latitude must be between -90 and 90.")
    if longitude is not None and not -180 <= longitude <= 180:
        raise ValidationDomainError("longitude must be between -180 and 180.")


def bounding_box(
    *, latitude: float, longitude: float, radius_km: float
) -> tuple[float, float, float, float]:
    """The smallest lat/lng square containing the search circle.

    A prefilter, not an answer: the square is larger than the circle, so it
    over-selects at the corners and `distance_km` below removes those. Doing it
    this way keeps the SQL to a `BETWEEN` on two indexable columns instead of
    trigonometry the database cannot use an index for.

    Longitude degrees converge as you leave the equator, so a kilometre is
    worth more longitude in Riyadh than in Jakarta — hence the `cos(latitude)`.
    Near the poles that cosine approaches zero and the box widens without
    bound, so it is clamped to the whole longitude range rather than dividing
    by something arbitrarily small.

    Returns `(min_lat, max_lat, min_lng, max_lng)`.
    """
    lat_delta = math.degrees(radius_km / _EARTH_RADIUS_KM)
    cos_lat = math.cos(math.radians(latitude))
    near_the_pole = cos_lat <= 0.01
    lng_delta = 180.0 if near_the_pole else math.degrees(radius_km / (_EARTH_RADIUS_KM * cos_lat))

    return (
        max(latitude - lat_delta, -90.0),
        min(latitude + lat_delta, 90.0),
        max(longitude - lng_delta, -180.0),
        min(longitude + lng_delta, 180.0),
    )


def distance_km(*, from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> float:
    """Great-circle distance, by the haversine formula.

    Haversine rather than the spherical law of cosines because the latter loses
    precision at small distances — exactly the distances a city search is made
    of, where two branches may be a few hundred metres apart.
    """
    lat1, lng1, lat2, lng2 = map(math.radians, (from_lat, from_lng, to_lat, to_lng))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def validate_availability_window(*, date_from: datetime, date_to: datetime, max_days: int) -> None:
    """Bounds how much calendar one anonymous request may ask for.

    The authenticated availability route is per provider, so its cost is capped
    by the caller naming one. The public route is per *service*, and answers for
    every provider qualified to perform it — so the same date range costs a
    multiple of it, chosen by a caller with no account and no principal to rate
    limit meaningfully.

    A shorter horizon than `availability_max_horizon_days` on purpose. A
    customer picking a time is looking at this week or next; nobody browses
    ninety days of a salon's calendar, but a scraper would happily ask for it.
    """
    if date_to <= date_from:
        raise ValidationDomainError("date_to must be after date_from.")
    if (date_to - date_from) > timedelta(days=max_days):
        raise ValidationDomainError(f"A public availability window may not exceed {max_days} days.")


def new_referral_token() -> str:
    """A fresh, unguessable referral token, returned to the customer once."""
    return secrets.token_urlsafe(_REFERRAL_TOKEN_BYTES)


def hash_referral_token(token: str) -> str:
    """What is actually stored.

    Only the hash goes in the table, for the same reason `queue` stores only a
    hash of a ticket token: reading the database must not hand anyone a working
    credential. Here the credential is worth money rather than entry — a
    referral is what turns a booking into a 35% commission line — so the rows
    that decide a salon's invoice should not also be a supply of usable tokens.

    Plain SHA-256 with no salt or stretching, deliberately: the input is 32
    bytes of CSPRNG output, so there is no dictionary to attack and a slow hash
    would only cost latency on every booking.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def referral_expiry(*, clicked_at: datetime) -> datetime:
    """When this click stops attributing (docs/11 section 3 rule 4)."""
    return clicked_at + timedelta(days=REFERRAL_WINDOW_DAYS)


def is_referral_live(*, expires_at: datetime, now: datetime | None = None) -> bool:
    """Whether a referral still attributes.

    Compared inclusively at neither end: a referral that expires exactly now is
    over. The direction is chosen the way ADR-0008 chooses every ambiguous
    case — against NOVA and in the salon's favour, because charging a salon for
    a customer it already had is the P1 that docs/11 section 3 names, and
    failing to charge for one we did introduce is merely lost revenue.
    """
    now = now or datetime.now(UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return now < expires_at
