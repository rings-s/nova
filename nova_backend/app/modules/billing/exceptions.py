"""billing · DOMAIN layer — module errors.

The rules that guard money live in `domain.py` beside what they protect
(`InvoiceAlreadyIssuedError`, `DowngradeBelowUsageError`,
`LineAlreadyReversedError`, `LineAlreadyInvoicedError`); this file holds the
lookups.
"""

from app.core.exceptions import ConflictError, NotFoundError


class SubscriptionNotFoundError(NotFoundError):
    code = "subscription_not_found"

    def __init__(self, business_id: object) -> None:
        super().__init__(f"No subscription exists for business '{business_id}'.")


class InvoiceNotFoundError(NotFoundError):
    code = "invoice_not_found"

    def __init__(self, invoice_id: object) -> None:
        super().__init__(f"Invoice '{invoice_id}' was not found.")


class CommissionLineNotFoundError(NotFoundError):
    code = "commission_line_not_found"

    def __init__(self, identifier: object) -> None:
        super().__init__(f"No commission line for '{identifier}'.")


class SubscriptionAlreadyExistsError(ConflictError):
    code = "subscription_exists"

    def __init__(self, business_id: object) -> None:
        super().__init__(f"Business '{business_id}' already has a subscription.")
