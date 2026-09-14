"""payment · DOMAIN layer — module errors.

The state-machine and money errors live in `domain.py` beside the rules they
guard (`InvalidPaymentTransition`, `PaymentNotCapturedError`,
`RefundExceedsCaptureError`, `WebhookSignatureError`); this file holds the rest.
"""

from app.core.exceptions import NotFoundError


class PaymentNotFoundError(NotFoundError):
    code = "payment_not_found"

    def __init__(self, payment_id: object) -> None:
        super().__init__(f"Payment '{payment_id}' was not found.")


class UnknownWebhookPaymentError(NotFoundError):
    """A webhook referencing a payment we have no record of.

    Returned as a 404 to the gateway, which is deliberate: a 5xx would make
    Moyasar retry forever for a payment that will never exist here.
    """

    code = "unknown_webhook_payment"

    def __init__(self, gateway_payment_id: str) -> None:
        super().__init__(f"No local payment matches gateway id '{gateway_payment_id}'.")
