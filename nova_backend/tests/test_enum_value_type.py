"""`EnumValue` stores an enum's value and still reads a legacy member name."""

import pytest

from app.db.types import EnumValue
from app.modules.booking.domain import BookingStatus

TYPE = EnumValue(BookingStatus, length=32)


def test_it_writes_the_value_not_the_member_name() -> None:
    assert TYPE.process_bind_param(BookingStatus.PENDING_PAYMENT, None) == "pending_payment"


def test_it_accepts_a_value_or_a_legacy_name_from_a_caller() -> None:
    assert TYPE.process_bind_param("confirmed", None) == "confirmed"
    assert TYPE.process_bind_param("CONFIRMED", None) == "confirmed"


def test_it_refuses_a_string_that_is_no_member() -> None:
    with pytest.raises(KeyError):
        TYPE.process_bind_param("nonsense", None)


def test_it_reads_a_value_and_a_row_written_before_values_were_stored() -> None:
    assert TYPE.process_result_value("in_service", None) is BookingStatus.IN_SERVICE
    assert TYPE.process_result_value("IN_SERVICE", None) is BookingStatus.IN_SERVICE


def test_null_stays_null() -> None:
    assert TYPE.process_bind_param(None, None) is None
    assert TYPE.process_result_value(None, None) is None
