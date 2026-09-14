"""payment · DOMAIN layer — module errors.

The state-machine and money errors live in `domain.py` beside the rules they
guard (`InvalidPaymentTransition`, `PaymentNotCapturedError`,
`RefundExceedsCaptureError`, `WebhookSignatureError`); this file holds the rest.
"""

from app.core.exceptions import DomainError, NotFoundError


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


class PaymentNotConfirmedError(DomainError):
    """A webhook claims a payment changed, and Moyasar's own record disagrees.

    Answered 503 so the gateway retries, since its API may briefly trail its own
    notification. A webhook forged with a leaked secret is never confirmed however
    often it is sent, so nothing it claims is recorded or applied.
    """

    status_code = 503
    code = "payment_not_confirmed"

    def __init__(self, gateway_payment_id: str, *, claimed: str, actual: str) -> None:
        super().__init__(
            f"The webhook reports payment '{gateway_payment_id}' as '{claimed}', "
            f"but the gateway reports '{actual or 'no status'}'."
        )
