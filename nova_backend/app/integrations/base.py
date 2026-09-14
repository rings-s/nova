"""Shared conventions for external system adapters (WhatsApp, Moyasar, Nextcloud, ...).

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


class IntegrationNotConfiguredError(RuntimeError):
    def __init__(self, integration_name: str) -> None:
        super().__init__(
            f"{integration_name} integration is not configured yet. "
            f"See docs/integrations/{integration_name.lower()}.md."
        )
