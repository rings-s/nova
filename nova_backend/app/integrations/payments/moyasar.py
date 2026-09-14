"""Moyasar payment gateway adapter.

Infrastructure only: this file owns HTTP, auth headers, and the vendor's JSON
shape. It knows nothing about bookings or deposits — `modules/payment` owns the
domain, and swapping gateways means writing another class satisfying
`PaymentGateway`, not touching that module.

To verify against live documentation before go-live: the exact webhook
signature scheme for this account (Moyasar has used both a shared secret in the
body and an HMAC header over time), which payment methods are enabled, and
whether void or only refund is supported for uncaptured authorisations. The
verification below accepts both schemes for that reason and is deliberately
strict about which one it is given.
"""

import hashlib
import hmac
import logging
from typing import Any, Protocol

import httpx

from app.integrations.base import IntegrationNotConfiguredError

logger = logging.getLogger(__name__)


class PaymentGateway(Protocol):
    """Operations NOVA needs from Moyasar."""

    async def create_payment(
        self,
        *,
        amount_minor: int,
        currency: str,
        description: str,
        callback_url: str,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Creates a payment. Returns the provider's payment object."""
        ...

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]: ...

    async def refund(
        self, payment_id: str, *, amount_minor: int | None = None
    ) -> dict[str, Any]: ...

    def verify_webhook(
        self, *, payload: bytes, signature: str | None, secret_token: str | None
    ) -> bool: ...


class NotConfiguredPaymentGateway:
    """Placeholder used until Moyasar credentials exist.

    Kept so the app boots, `/docs` renders, and every other module is
    developable without a live payment account. Any actual attempt to move
    money fails loudly rather than silently succeeding.
    """

    async def create_payment(
        self,
        *,
        amount_minor: int,
        currency: str,
        description: str,
        callback_url: str,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        raise IntegrationNotConfiguredError("Moyasar")

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        raise IntegrationNotConfiguredError("Moyasar")

    async def refund(self, payment_id: str, *, amount_minor: int | None = None) -> dict[str, Any]:
        raise IntegrationNotConfiguredError("Moyasar")

    def verify_webhook(
        self, *, payload: bytes, signature: str | None, secret_token: str | None
    ) -> bool:
        # Fails closed. An unconfigured gateway must never be able to confirm
        # a booking by accepting an unverified webhook.
        return False


class MoyasarGateway:
    """Live adapter. Basic auth with the secret key, per Moyasar's API."""

    def __init__(
        self,
        *,
        api_key: str,
        webhook_secret: str | None = None,
        base_url: str = "https://api.moyasar.com/v1",
        timeout_seconds: float = 15.0,
    ) -> None:
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            # Moyasar authenticates with the secret key as the basic-auth
            # username and an empty password.
            auth=(self.api_key, ""),
            timeout=self.timeout_seconds,
        )

    async def create_payment(
        self,
        *,
        amount_minor: int,
        currency: str,
        description: str,
        callback_url: str,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            # Integer minor units (halalas). Never a float — see
            # `payment.domain.to_minor_units`.
            "amount": amount_minor,
            "currency": currency,
            "description": description,
            "callback_url": callback_url,
        }
        if metadata:
            payload["metadata"] = metadata

        async with self._client() as client:
            response = await client.post("/payments", json=payload)
            response.raise_for_status()
            return response.json()

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        """Authoritative read, used to confirm what a webhook claimed."""
        async with self._client() as client:
            response = await client.get(f"/payments/{payment_id}")
            response.raise_for_status()
            return response.json()

    async def refund(self, payment_id: str, *, amount_minor: int | None = None) -> dict[str, Any]:
        payload = {"amount": amount_minor} if amount_minor is not None else {}
        async with self._client() as client:
            response = await client.post(f"/payments/{payment_id}/refund", json=payload)
            response.raise_for_status()
            return response.json()

    def verify_webhook(
        self, *, payload: bytes, signature: str | None, secret_token: str | None
    ) -> bool:
        """Verifies an inbound webhook. Fails closed in every ambiguous case.

        Two schemes are accepted because Moyasar has used both:

          1. An HMAC-SHA256 header over the raw request body.
          2. A shared `secret_token` field inside the payload.

        Both comparisons are constant-time. If no webhook secret is configured
        this returns False rather than True — an unverifiable webhook must not
        be allowed to capture a payment, and "we forgot to set the secret" is
        exactly when that protection matters most.
        """
        if not self.webhook_secret:
            logger.error("moyasar_webhook_secret_missing")
            return False

        if signature:
            expected = hmac.new(self.webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
            # Some senders prefix the scheme, e.g. "sha256=abc123".
            presented = signature.split("=", 1)[-1].strip()
            return hmac.compare_digest(presented, expected)

        if secret_token:
            return hmac.compare_digest(secret_token, self.webhook_secret)

        return False


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
