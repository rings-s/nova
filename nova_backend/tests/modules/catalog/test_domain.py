"""Pure domain tests for catalog — no database."""

from decimal import Decimal

import pytest

from app.core.exceptions import ValidationDomainError
from app.modules.catalog.domain import (
    validate_coordinates,
    validate_service_duration,
    validate_service_price,
)


class TestServiceDuration:
    def test_accepts_a_normal_treatment(self):
        assert validate_service_duration(45) == 45

    def test_rejects_absurdly_short(self):
        with pytest.raises(ValidationDomainError):
            validate_service_duration(1)

    def test_rejects_longer_than_a_working_day(self):
        with pytest.raises(ValidationDomainError):
            validate_service_duration(9 * 60)

    def test_rejects_off_grid_duration(self):
        """Availability is generated on a 5-minute grid."""
        with pytest.raises(ValidationDomainError):
            validate_service_duration(47)


class TestServicePrice:
    def test_accepts_two_decimal_places(self):
        assert validate_service_price(Decimal("150.50")) == Decimal("150.50")

    def test_accepts_free_service(self):
        assert validate_service_price(Decimal("0")) == Decimal("0")

    def test_rejects_negative(self):
        with pytest.raises(ValidationDomainError):
            validate_service_price(Decimal("-1.00"))

    def test_rejects_sub_fils_precision(self):
        with pytest.raises(ValidationDomainError):
            validate_service_price(Decimal("10.001"))


class TestCoordinates:
    def test_accepts_both_or_neither(self):
        validate_coordinates(24.7136, 46.6753)
        validate_coordinates(None, None)

    def test_rejects_half_a_pair(self):
        """A lone latitude silently breaks map search."""
        with pytest.raises(ValidationDomainError):
            validate_coordinates(24.7136, None)

    def test_rejects_out_of_range(self):
        with pytest.raises(ValidationDomainError):
            validate_coordinates(91.0, 46.6753)
        with pytest.raises(ValidationDomainError):
            validate_coordinates(24.7136, 181.0)
