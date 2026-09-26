"""Moyasar payment gateway adapter.

Infrastructure only: this file owns HTTP, auth, and the vendor's JSON shape. It
knows nothing about bookings or deposits — `modules/payment` owns the domain,
and swapping gateways means writing another class satisfying `PaymentGateway`,
not touching that module.

Written against Moyasar's API reference (https://docs.moyasar.com/api/):

- **Checkout is an invoice** (`POST /v1/invoices`). The server sets the
  amount and gets back `url`, Moyasar's hosted checkout page, where the payer
  chooses mada, a card, Apple Pay or STC Pay (whichever the account enables).
  Card data never reaches NOVA. `POST /v1/payments` is not used to start a
  payment: it requires a `source` (raw card details or a token made in the
  browser), which is the Payment Form's job, not a server's.
- **Amounts are integers in the smallest unit** (halalas for SAR); an invoice
  must be at least 100.
- **Auth is HTTP Basic**, the secret key (`sk_test_…`/`sk_live_…`) as the
  username and an empty password. A publishable key (`pk_…`) cannot create
  invoices or read payments, and is refused at configuration time.
- **Webhooks carry `secret_token` in the JSON body**, the shared secret set on
  the webhook in the dashboard. There is no signature header; the payload is
  `{id, type, created_at, secret_token, account_name, live, data}`, with the
  payment in `data` for `payment_*` events. A non-2xx is retried five more
  times (1 min, 10 min, 30 min, 1 h, 2 h).
- **A notification is not proof.** Moyasar's own guidance is to fetch the
  payment and check `status`, `amount` and `currency` before fulfilling. The
  payment module does exactly that with `fetch_payment`/`fetch_invoice`.
"""

import hmac
import logging
from datetime import datetime
from typing import Any, Protocol

import httpx

from app.core.exceptions import DomainError
from app.integrations.base import IntegrationNotConfiguredError

logger = logging.getLogger(__name__)

#: Moyasar's floor for an invoice amount, in the smallest currency unit.
MIN_INVOICE_AMOUNT_MINOR = 100


class PaymentGatewayError(DomainError):
    """Moyasar answered with an error, or could not be reached.

    A 502 rather than a 500: nothing in NOVA broke, and the request may well
    succeed if tried again. Moyasar's own message is logged, not returned —
    it can name account settings a payer has no business seeing.
    """

    status_code = 502
    code = "payment_gateway_error"
    retryable = True

    def __init__(
        self, message: str = "The payment provider could not complete the request."
    ) -> None:
        super().__init__(message)


class PaymentGateway(Protocol):
    """Operations NOVA needs from Moyasar."""

    async def create_invoice(
        self,
        *,
        amount_minor: int,
        currency: str,
        description: str,
        success_url: str,
        back_url: str,
        expired_at: datetime | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Opens a hosted checkout. Returns the invoice, with its `url`."""
        ...

    async def fetch_invoice(self, invoice_id: str) -> dict[str, Any]: ...

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]: ...

    async def refund(
        self, payment_id: str, *, amount_minor: int | None = None
    ) -> dict[str, Any]: ...

    def verify_webhook(self, *, secret_token: str | None) -> bool: ...


class NotConfiguredPaymentGateway:
    """Placeholder used until Moyasar credentials exist.

    Kept so the app boots, `/docs` renders, and every other module is
    developable without a live payment account. Any actual attempt to move
    money fails loudly rather than silently succeeding.
    """

    async def create_invoice(
        self,
        *,
        amount_minor: int,
        currency: str,
        description: str,
        success_url: str,
        back_url: str,
        expired_at: datetime | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        raise IntegrationNotConfiguredError("Moyasar")

    async def fetch_invoice(self, invoice_id: str) -> dict[str, Any]:
        raise IntegrationNotConfiguredError("Moyasar")

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        raise IntegrationNotConfiguredError("Moyasar")

    async def refund(self, payment_id: str, *, amount_minor: int | None = None) -> dict[str, Any]:
        raise IntegrationNotConfiguredError("Moyasar")

    def verify_webhook(self, *, secret_token: str | None) -> bool:
        # Fails closed. An unconfigured gateway must never be able to confirm
        # a booking by accepting an unverified webhook.
        return False


class MoyasarGateway:
    """Live adapter for `https://api.moyasar.com/v1`."""

    def __init__(
        self,
        *,
        api_key: str,
        webhook_secret: str | None = None,
        base_url: str = "https://api.moyasar.com/v1",
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        #: For tests: an `httpx.MockTransport` in place of the network.
        self.transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            # Basic auth: the secret key as username, an empty password.
            auth=(self.api_key, ""),
            timeout=self.timeout_seconds,
            headers={"Accept": "application/json"},
            transport=self.transport,
        )

    async def _request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            async with self._client() as client:
                response = await client.request(method, path, json=json)
        except httpx.HTTPError as exc:
            logger.warning("moyasar_unreachable", extra={"path": path, "error": repr(exc)})
            raise PaymentGatewayError() from exc

        if response.is_success:
            return response.json()

        # Moyasar's errors are `{type, message, errors}`. Logged for whoever
        # operates the account; the caller gets the generic envelope.
        try:
            detail = response.json()
        except ValueError:
            detail = {"body": response.text[:500]}
        logger.error(
            "moyasar_error",
            extra={"path": path, "status": response.status_code, "detail": detail},
        )
        if response.status_code == 401:
            # A wrong or revoked key is a deployment problem, not a payer's.
            raise PaymentGatewayError(
                "The payment provider rejected this deployment's credentials."
            )
        raise PaymentGatewayError()

    async def create_invoice(
        self,
        *,
        amount_minor: int,
        currency: str,
        description: str,
        success_url: str,
        back_url: str,
        expired_at: datetime | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """`POST /invoices`. The payer completes it at the returned `url`."""
        payload: dict[str, Any] = {
            # Integer minor units. Never a float — see `payment.domain.to_minor_units`.
            "amount": amount_minor,
            "currency": currency,
            "description": description,
            # Where the payer lands once paid, and where "back" takes them.
            "success_url": success_url,
            "back_url": back_url,
        }
        if expired_at is not None:
            payload["expired_at"] = expired_at.isoformat()
        if metadata:
            # Both keys and values must be strings.
            payload["metadata"] = {str(k): str(v) for k, v in metadata.items()}
        return await self._request("POST", "/invoices", json=payload)

    async def fetch_invoice(self, invoice_id: str) -> dict[str, Any]:
        """`GET /invoices/{id}`: the invoice with every payment attempt on it."""
        return await self._request("GET", f"/invoices/{invoice_id}")

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        """`GET /payments/{id}`: the authoritative record a webhook is checked against."""
        return await self._request("GET", f"/payments/{payment_id}")

    async def refund(self, payment_id: str, *, amount_minor: int | None = None) -> dict[str, Any]:
        """`POST /payments/{id}/refund`. No amount refunds whatever remains."""
        payload = {"amount": amount_minor} if amount_minor is not None else {}
        return await self._request("POST", f"/payments/{payment_id}/refund", json=payload)

    def verify_webhook(self, *, secret_token: str | None) -> bool:
        """Checks the `secret_token` a webhook carries in its body.

        Constant-time, and closed in every ambiguous case: with no secret
        configured nothing verifies, because an unverifiable webhook must not
        be able to capture a payment, and "we forgot to set the secret" is
        exactly when that protection matters most.
        """
        if not self.webhook_secret:
            logger.error("moyasar_webhook_secret_missing")
            return False
        if not secret_token:
            return False
        return hmac.compare_digest(secret_token.encode(), self.webhook_secret.encode())


def build_payment_gateway(
    *,
    api_key: str | None,
    webhook_secret: str | None,
    base_url: str,
) -> PaymentGateway:
    """Picks the live adapter or the placeholder, based on configuration."""
    if not api_key:
        return NotConfiguredPaymentGateway()
    return MoyasarGateway(api_key=api_key, webhook_secret=webhook_secret, base_url=base_url)


__all__ = [
    "MIN_INVOICE_AMOUNT_MINOR",
    "MoyasarGateway",
    "NotConfiguredPaymentGateway",
    "PaymentGateway",
    "PaymentGatewayError",
    "build_payment_gateway",
]
