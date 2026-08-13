from typing import Protocol

from app.integrations.base import IntegrationNotConfiguredError


class PaymentGateway(Protocol):
    """Operations NOVA needs from Moyasar.

    To verify: supported payment methods for this account, webhook signature
    scheme, refund/void semantics. See docs/integrations/payments-moyasar.md.
    """

    async def create_payment(self, *, amount_minor: int, currency: str, description: str) -> str:
        """Creates a payment/invoice. Returns the provider payment id."""
        ...

    async def verify_webhook(self, *, payload: bytes, signature: str) -> bool: ...


class NotConfiguredPaymentGateway:
    """Placeholder used until Moyasar credentials/integration exist."""

    async def create_payment(self, *, amount_minor: int, currency: str, description: str) -> str:
        raise IntegrationNotConfiguredError("Moyasar")

    async def verify_webhook(self, *, payload: bytes, signature: str) -> bool:
        raise IntegrationNotConfiguredError("Moyasar")
