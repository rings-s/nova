"""What the platform console shows and may do. Pure — no database."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.admin.domain import (
    ACTIONS,
    MASK,
    AdminAction,
    action_spec,
    actions_for,
    clean_reason,
    decode_row_id,
    display_value,
    encode_row_id,
    group_of,
    is_masked_column,
)


@pytest.mark.parametrize(
    "column",
    ["password_hash", "token_hash", "qr_token_hash", "hold_token", "request_fingerprint"],
)
def test_credentials_are_never_shown(column: str) -> None:
    assert display_value(column, "s3cret-value-123456") == MASK
    assert is_masked_column(column)


def test_gateway_references_keep_only_their_last_four_characters() -> None:
    shown = display_value("gateway_payment_id", "pay_0123456789abcdef")
    assert shown == f"{MASK}cdef"
    # A short value would be mostly visible through its last four.
    assert display_value("gateway_invoice_id", "inv_1") == MASK


def test_ordinary_columns_come_back_json_safe() -> None:
    row_id = uuid4()
    at = datetime(2026, 10, 11, 9, 30, tzinfo=UTC)
    assert display_value("id", row_id) == str(row_id)
    assert display_value("price", Decimal("150.00")) == "150.00"
    assert display_value("starts_at", at) == at.isoformat()
    assert display_value("email", "a@example.com") == "a@example.com"
    assert display_value("notes", None) is None
    assert not is_masked_column("email")


def test_secrets_inside_json_payloads_are_scrubbed_at_any_depth() -> None:
    payload = {
        "id": "evt_1",
        "secret_token": "whsec",
        "data": {"metadata": {"qr_payload": "QR", "amount": 100}},
        "items": [{"Authorization": "Bearer x", "ok": True}],
    }
    assert display_value("payload", payload) == {
        "id": "evt_1",
        "secret_token": MASK,
        "data": {"metadata": {"qr_payload": MASK, "amount": 100}},
        "items": [{"Authorization": MASK, "ok": True}],
    }


def test_a_composite_key_round_trips_through_one_path_segment() -> None:
    a, b = uuid4(), uuid4()
    encoded = encode_row_id([a, b])
    assert decode_row_id(encoded, 2) == [str(a), str(b)]
    assert decode_row_id(encoded, 1) is None
    assert decode_row_id("", 1) is None


def test_every_action_names_a_table_the_console_groups() -> None:
    for spec in ACTIONS:
        assert group_of(spec.table) != "platform", spec


def test_actions_are_looked_up_per_table() -> None:
    assert {spec.action for spec in actions_for("users")} == {
        AdminAction.DEACTIVATE_USER,
        AdminAction.REACTIVATE_USER,
        AdminAction.REVOKE_SESSIONS,
    }
    assert actions_for("payments") == []
    # An action only exists on its own table.
    assert action_spec("businesses", "deactivate_user") is None
    assert action_spec("users", "deactivate_user") is not None


def test_a_cancellation_needs_a_reason_and_keeps_it_short() -> None:
    spec = action_spec("bookings", "cancel_booking")
    assert spec is not None
    with pytest.raises(ValueError):
        clean_reason(spec, "   ")
    with pytest.raises(ValueError):
        clean_reason(spec, "x" * 501)
    assert clean_reason(spec, "  provider ill ") == "provider ill"

    optional = action_spec("users", "revoke_sessions")
    assert optional is not None
    assert clean_reason(optional, None) is None
