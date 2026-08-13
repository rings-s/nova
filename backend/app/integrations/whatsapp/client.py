from typing import Protocol

from app.integrations.base import IntegrationNotConfiguredError


class WhatsAppClient(Protocol):
    """Operations NOVA needs from the WhatsApp Business Platform via an approved BSP.

    To verify: which BSP, template approval workflow, 24-hour session-window
    rules, webhook delivery guarantees. See docs/integrations/whatsapp.md.
    """

    async def send_template_message(
        self, *, to_phone: str, template_name: str, params: dict[str, str]
    ) -> str:
        """Sends an approved template message. Returns the provider message id."""
        ...


class NotConfiguredWhatsAppClient:
    """Placeholder used until a real BSP integration is implemented."""

    async def send_template_message(
        self, *, to_phone: str, template_name: str, params: dict[str, str]
    ) -> str:
        raise IntegrationNotConfiguredError("WhatsApp")
