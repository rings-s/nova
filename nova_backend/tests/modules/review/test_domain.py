"""Rating rules and ranking. Pure — no database."""

import pytest

from app.core.exceptions import ValidationDomainError
from app.modules.catalog.domain import (
    RATING_PRIOR_MEAN,
    rating_average,
    rating_score,
)
from app.modules.discovery.domain import resolve_search_order
from app.modules.review.domain import is_reviewable, normalize_comment, validate_rating


@pytest.mark.parametrize("rating", [1, 3, 5])
def test_whole_stars_from_one_to_five_are_ratings(rating: int) -> None:
    assert validate_rating(rating) == rating


@pytest.mark.parametrize("rating", [0, 6, -1, True])
def test_anything_else_is_refused(rating: int) -> None:
    with pytest.raises(ValidationDomainError):
        validate_rating(rating)


def test_a_blank_comment_is_no_comment() -> None:
    assert normalize_comment("   ") is None
    assert normalize_comment(None) is None
    assert normalize_comment("  lovely  ") == "lovely"


def test_a_comment_has_a_length_limit() -> None:
    with pytest.raises(ValidationDomainError):
        normalize_comment("x" * 1001)


@pytest.mark.parametrize(
    ("status", "allowed"),
    [("completed", True), ("confirmed", False), ("cancelled", False), ("no_show", False)],
)
def test_only_a_completed_visit_can_be_rated(status: str, allowed: bool) -> None:
    assert is_reviewable(status) is allowed


def test_nobody_has_rated_means_no_average() -> None:
    assert rating_average(0, 0) is None
    assert rating_average(9, 2) == 4.5


def test_an_unrated_business_scores_the_prior() -> None:
    assert rating_score(0, 0) == RATING_PRIOR_MEAN


def test_one_perfect_visit_does_not_outrank_many_excellent_ones() -> None:
    """The reason the ranking is not a plain average."""
    one_perfect = rating_score(5, 1)
    two_hundred_at_4_8 = rating_score(960, 200)
    assert two_hundred_at_4_8 > one_perfect


def test_more_evidence_at_the_same_average_ranks_higher() -> None:
    assert rating_score(50, 10) > rating_score(5, 1)


def test_default_order_is_nearest_when_located_and_by_name_otherwise() -> None:
    assert resolve_search_order("default", located=True) == "distance"
    assert resolve_search_order("default", located=False) == "name"
    assert resolve_search_order("rating", located=False) == "rating"
    assert resolve_search_order("rating", located=True) == "rating"


def test_distance_needs_somewhere_to_measure_from() -> None:
    with pytest.raises(ValidationDomainError):
        resolve_search_order("distance", located=False)
