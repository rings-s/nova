"""The Moyasar adapter against Moyasar's documented API, with the network
replaced by `httpx.MockTransport`. No database, no account.

What is pinned here is what the API reference says a request must look like
(https://docs.moyasar.com/api/): Basic auth with the secret key, integer minor
units, the invoice fields, and the webhook's `secret_token`.
"""

import base64
import json
from datetime import UTC, datetime

import httpx
import pytest

from app.integrations.payments.moyasar import (
    MoyasarGateway,
    NotConfiguredPaymentGateway,
    PaymentGatewayError,
    build_payment_gateway,
)

SECRET_KEY = "sk_test_abc123"


def _gateway(handler, *, webhook_secret: str | None = "whsec") -> MoyasarGateway:
    return MoyasarGateway(
        api_key=SECRET_KEY,
        webhook_secret=webhook_secret,
        transport=httpx.MockTransport(handler),
    )


async def test_an_invoice_is_opened_with_the_documented_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            201,
            json={
                "id": "inv_1",
                "status": "initiated",
                "url": "https://checkout.moyasar.com/invoices/inv_1",
            },
        )

    invoice = await _gateway(handler).create_invoice(
        amount_minor=15000,
        currency="SAR",
        description="NOVA booking ABC",
        success_url="https://app.example/bookings?payment=p1",
        back_url="https://app.example/bookings?payment=p1",
        expired_at=datetime(2026, 9, 23, 12, 0, tzinfo=UTC),
        metadata={"booking_id": "b1"},
    )

    assert invoice["url"].startswith("https://checkout.moyasar.com/")
    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == "https://api.moyasar.com/v1/invoices"
    # HTTP Basic: the secret key as username, an empty password.
    expected = base64.b64encode(f"{SECRET_KEY}:".encode()).decode()
    assert request.headers["Authorization"] == f"Basic {expected}"
    body = json.loads(request.content)
    assert body == {
        "amount": 15000,
        "currency": "SAR",
        "description": "NOVA booking ABC",
        "success_url": "https://app.example/bookings?payment=p1",
        "back_url": "https://app.example/bookings?payment=p1",
        "expired_at": "2026-09-23T12:00:00+00:00",
        "metadata": {"booking_id": "b1"},
    }
    # Minor units are an integer on the wire, never "150.00" or 150.0.
    assert isinstance(body["amount"], int)


@pytest.mark.parametrize(
    ("call", "method", "path"),
    [
        (lambda g: g.fetch_invoice("inv_1"), "GET", "/v1/invoices/inv_1"),
        (lambda g: g.fetch_payment("pay_1"), "GET", "/v1/payments/pay_1"),
        (lambda g: g.refund("pay_1", amount_minor=500), "POST", "/v1/payments/pay_1/refund"),
    ],
)
async def test_each_call_goes_where_the_reference_says(call, method, path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "x"})

    await call(_gateway(handler))

    assert seen[0].method == method
    assert seen[0].url.path == path


async def test_a_partial_refund_names_its_amount_and_a_full_one_does_not() -> None:
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(200, json={"id": "pay_1", "status": "refunded"})

    gateway = _gateway(handler)
    await gateway.refund("pay_1", amount_minor=500)
    await gateway.refund("pay_1")

    assert json.loads(bodies[0]) == {"amount": 500}
    assert json.loads(bodies[1]) == {}


async def test_a_moyasar_error_is_a_retryable_502_that_leaks_nothing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "type": "invalid_request_error",
                "message": "Validation Failed",
                "errors": {"amount": ["must be greater than or equal to 100"]},
            },
        )

    with pytest.raises(PaymentGatewayError) as raised:
        await _gateway(handler).fetch_payment("pay_1")

    assert raised.value.status_code == 502
    assert raised.value.retryable is True
    assert "Validation" not in raised.value.message


async def test_a_rejected_key_says_so() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"type": "authentication_error", "message": "Invalid"})

    with pytest.raises(PaymentGatewayError, match="credentials"):
        await _gateway(handler).fetch_payment("pay_1")


async def test_an_unreachable_moyasar_is_a_502_not_a_crash() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(PaymentGatewayError):
        await _gateway(handler).fetch_invoice("inv_1")


class TestWebhookToken:
    def test_the_configured_secret_verifies(self) -> None:
        assert _gateway(lambda r: httpx.Response(200)).verify_webhook(secret_token="whsec")

    @pytest.mark.parametrize("token", [None, "", "whsec ", "WHSEC", "other"])
    def test_anything_else_does_not(self, token) -> None:
        assert not _gateway(lambda r: httpx.Response(200)).verify_webhook(secret_token=token)

    def test_with_no_secret_configured_nothing_verifies(self) -> None:
        gateway = _gateway(lambda r: httpx.Response(200), webhook_secret=None)
        assert not gateway.verify_webhook(secret_token="")
        assert not gateway.verify_webhook(secret_token="anything")

    def test_the_placeholder_fails_closed(self) -> None:
        assert not NotConfiguredPaymentGateway().verify_webhook(secret_token="anything")


def test_without_a_key_the_placeholder_is_used() -> None:
    gateway = build_payment_gateway(
        api_key=None, webhook_secret=None, base_url="https://api.moyasar.com/v1"
    )
    assert isinstance(gateway, NotConfiguredPaymentGateway)
