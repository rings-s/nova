"""Shared conventions for external system adapters (WhatsApp, Moyasar, ...).

Each integration defines:
- A `Protocol` describing only the operations NOVA actually calls, not the
  vendor's full API surface.
- A placeholder adapter that raises `IntegrationNotConfiguredError` until a
  real implementation exists, so the app runs and is developable without any
  external account being live.

This keeps every external system a replaceable adapter: swapping WhatsApp BSPs
or payment gateways means writing a new class satisfying the same Protocol,
not touching the module code that depends on it.
"""

from app.core.exceptions import DomainError


class IntegrationNotConfiguredError(DomainError):
    """An adapter was called on a deployment that has no credentials for it.

    A 503 in the error envelope, not retryable: nothing failed, the feature is
    off here, and asking again will not turn it on. As a bare `RuntimeError` it
    reached the catch-all handler, so every such call answered `internal_error`
    and logged a traceback as if the server had broken.
    """

    status_code = 503
    code = "integration_not_configured"

    def __init__(self, integration_name: str) -> None:
        super().__init__(f"{integration_name} is not configured on this deployment.")
        self.integration_name = integration_name
