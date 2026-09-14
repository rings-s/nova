"""Discovery domain rules — pure, no database, no HTTP.

Two things are being protected here, and only one of them is geometry.

The arithmetic matters because a bounding box that is too small silently hides
salons a customer asked for, and one that is too large reports a branch as
"3km away" when it is not.

The referral rules matter more. They decide whether a salon is charged 35%
(docs/11 section 3), so every ambiguous case has a documented direction to fail
in, and these tests are what hold it there.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ValidationDomainError
from app.modules.discovery.domain import (
    MAX_SEARCH_RADIUS_KM,
    REFERRAL_WINDOW_DAYS,
    bounding_box,
    distance_km,
    hash_referral_token,
    is_referral_live,
    new_referral_token,
    normalize_search_term,
    referral_expiry,
    validate_availability_window,
    validate_coordinate_pair,
    validate_radius_km,
)

#: Riyadh, roughly. Used as the origin for every geo assertion below.
RIYADH = (24.7136, 46.6753)


class TestSearchTerms:
    def test_a_usable_term_survives(self):
        assert normalize_search_term("  Haircut ") == "Haircut"

    def test_arabic_is_not_mangled(self):
        assert normalize_search_term("قص شعر") == "قص شعر"

    @pytest.mark.parametrize("term", [None, "", "  ", "a", " x "])
    def test_too_short_to_be_worth_querying_becomes_nothing(self, term):
        """The caller reads None as "no term" and lists instead of searching.

        Raising would turn a customer backspacing over their query into an
        error; matching would scan the table to prove that "a" matches most of
        it.
        """
        assert normalize_search_term(term) is None

    def test_wildcards_are_escaped(self):
        """`%` and `_` are ILIKE wildcards, not literal characters.

        Unescaped, a customer searching for "50% off" matches every row, and
        a search for "_" matches every row that has any character at all.
        """
        assert normalize_search_term("50% off") == r"50\% off"
        assert normalize_search_term("a_b") == r"a\_b"
        assert normalize_search_term(r"back\slash") == "back\\\\slash"


class TestCoordinateValidation:
    def test_a_full_pair_is_accepted(self):
        validate_coordinate_pair(*RIYADH)

    def test_no_pair_at_all_is_accepted(self):
        validate_coordinate_pair(None, None)

    @pytest.mark.parametrize("pair", [(24.7, None), (None, 46.6)])
    def test_half_a_pair_is_refused(self, pair):
        """A latitude with no longitude is a search of the whole country."""
        with pytest.raises(ValidationDomainError):
            validate_coordinate_pair(*pair)

    @pytest.mark.parametrize("pair", [(91.0, 0.0), (-91.0, 0.0), (0.0, 181.0), (0.0, -181.0)])
    def test_out_of_range_is_refused(self, pair):
        with pytest.raises(ValidationDomainError):
            validate_coordinate_pair(*pair)

    def test_radius_must_be_positive(self):
        with pytest.raises(ValidationDomainError):
            validate_radius_km(0)

    def test_radius_is_capped(self):
        """Uncapped, `radius_km=40000` is a full table scan in a filter."""
        validate_radius_km(MAX_SEARCH_RADIUS_KM)
        with pytest.raises(ValidationDomainError):
            validate_radius_km(MAX_SEARCH_RADIUS_KM + 1)


class TestDistance:
    def test_a_point_is_zero_from_itself(self):
        assert distance_km(
            from_lat=RIYADH[0], from_lng=RIYADH[1], to_lat=RIYADH[0], to_lng=RIYADH[1]
        ) == pytest.approx(0.0)

    def test_riyadh_to_jeddah(self):
        """~845km by great circle. Within 1% is plenty for a search radius."""
        km = distance_km(from_lat=24.7136, from_lng=46.6753, to_lat=21.4858, to_lng=39.1925)
        assert km == pytest.approx(845, rel=0.01)

    def test_it_is_symmetric(self):
        there = distance_km(from_lat=24.7, from_lng=46.6, to_lat=21.4, to_lng=39.1)
        back = distance_km(from_lat=21.4, from_lng=39.1, to_lat=24.7, to_lng=46.6)
        assert there == pytest.approx(back)

    def test_short_distances_stay_precise(self):
        """A few hundred metres is the distance a city search is made of.

        This is the case the spherical law of cosines loses precision on, and
        the reason `distance_km` uses haversine instead.
        """
        km = distance_km(from_lat=24.7136, from_lng=46.6753, to_lat=24.7136, to_lng=46.6803)
        assert km == pytest.approx(0.505, abs=0.02)


class TestBoundingBox:
    def test_it_contains_the_circle(self):
        """The box must never be smaller than the radius it stands in for.

        If it is, the SQL prefilter drops branches that are genuinely within
        range and no amount of exact maths afterwards puts them back.
        """
        radius = 10.0
        min_lat, max_lat, min_lng, max_lng = bounding_box(
            latitude=RIYADH[0], longitude=RIYADH[1], radius_km=radius
        )

        # Due north and due east at exactly the radius must fall inside.
        north = distance_km(
            from_lat=RIYADH[0], from_lng=RIYADH[1], to_lat=max_lat, to_lng=RIYADH[1]
        )
        east = distance_km(from_lat=RIYADH[0], from_lng=RIYADH[1], to_lat=RIYADH[0], to_lng=max_lng)
        assert north >= radius - 0.01
        assert east >= radius - 0.01
        assert min_lat < RIYADH[0] < max_lat
        assert min_lng < RIYADH[1] < max_lng

    def test_longitude_widens_away_from_the_equator(self):
        """A kilometre buys more longitude in Riyadh than at the equator.

        Ignoring the convergence makes the box too narrow in Saudi Arabia, and
        the whole prefilter starts hiding results.
        """
        _, _, eq_min, eq_max = bounding_box(latitude=0.0, longitude=0.0, radius_km=10)
        _, _, ry_min, ry_max = bounding_box(latitude=60.0, longitude=0.0, radius_km=10)
        assert (ry_max - ry_min) > (eq_max - eq_min)

    def test_near_the_pole_it_clamps_instead_of_exploding(self):
        """cos(latitude) approaches zero at the pole; dividing by it does not end well."""
        _, _, min_lng, max_lng = bounding_box(latitude=89.999, longitude=0.0, radius_km=50)
        assert (min_lng, max_lng) == (-180.0, 180.0)

    def test_it_never_leaves_the_globe(self):
        min_lat, max_lat, min_lng, max_lng = bounding_box(
            latitude=89.0, longitude=179.0, radius_km=MAX_SEARCH_RADIUS_KM
        )
        assert -90.0 <= min_lat <= max_lat <= 90.0
        assert -180.0 <= min_lng <= max_lng <= 180.0


class TestReferralTokens:
    def test_every_token_is_different(self):
        assert len({new_referral_token() for _ in range(200)}) == 200

    def test_the_token_is_not_recoverable_from_what_is_stored(self):
        """Only the hash is persisted, so the table is not a supply of tokens."""
        token = new_referral_token()
        stored = hash_referral_token(token)
        assert token not in stored
        assert len(stored) == 64

    def test_hashing_is_deterministic(self):
        """The booking path finds a referral by hashing the token it was given."""
        token = new_referral_token()
        assert hash_referral_token(token) == hash_referral_token(token)


class TestTheAttributionWindow:
    """docs/11 section 3 rule 4: a click attributes for 30 days."""

    def test_the_window_is_thirty_days(self):
        assert REFERRAL_WINDOW_DAYS == 30

    def test_expiry_is_thirty_days_after_the_click(self):
        clicked = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
        assert referral_expiry(clicked_at=clicked) == clicked + timedelta(days=30)

    def test_a_fresh_referral_is_live(self):
        now = datetime.now(UTC)
        assert is_referral_live(expires_at=now + timedelta(days=1), now=now)

    def test_a_referral_one_second_past_the_window_is_not(self):
        now = datetime.now(UTC)
        assert not is_referral_live(expires_at=now - timedelta(seconds=1), now=now)

    def test_expiring_exactly_now_is_over(self):
        """The boundary resolves against NOVA, per ADR-0008.

        Charging a salon for a customer it already had is the P1 docs/11 names;
        failing to charge for one we did introduce is only lost revenue. So the
        tie goes to the salon.
        """
        now = datetime.now(UTC)
        assert not is_referral_live(expires_at=now, now=now)

    def test_a_naive_timestamp_is_read_as_utc(self):
        """Postgres can hand back a naive datetime; comparing it to an aware
        `now` raises TypeError, which would 500 the booking rather than simply
        declining to attribute it."""
        now = datetime.now(UTC)
        naive_future = (now + timedelta(days=2)).replace(tzinfo=None)
        assert is_referral_live(expires_at=naive_future, now=now)


class TestThePublicAvailabilityWindow:
    """Bounds what one anonymous request may ask the calendar for."""

    def test_a_normal_window_is_accepted(self):
        now = datetime.now(UTC)
        validate_availability_window(date_from=now, date_to=now + timedelta(days=7), max_days=14)

    def test_exactly_the_maximum_is_accepted(self):
        now = datetime.now(UTC)
        validate_availability_window(date_from=now, date_to=now + timedelta(days=14), max_days=14)

    def test_a_window_past_the_maximum_is_refused(self):
        now = datetime.now(UTC)
        with pytest.raises(ValidationDomainError):
            validate_availability_window(
                date_from=now, date_to=now + timedelta(days=15), max_days=14
            )

    def test_a_backwards_window_is_refused(self):
        now = datetime.now(UTC)
        with pytest.raises(ValidationDomainError):
            validate_availability_window(
                date_from=now, date_to=now - timedelta(days=1), max_days=14
            )

    def test_an_empty_window_is_refused(self):
        now = datetime.now(UTC)
        with pytest.raises(ValidationDomainError):
            validate_availability_window(date_from=now, date_to=now, max_days=14)
