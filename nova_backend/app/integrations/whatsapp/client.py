"""WhatsApp Business Platform adapter (via an approved BSP).

Infrastructure only: HTTP, auth, and the provider's message envelope. The
`notification` module owns consent, quiet hours, and which template to send.

Two facts about WhatsApp that shape this file:

  1. Outside a 24-hour customer-initiated session window, only *pre-approved
     templates* may be sent. Free text is rejected by the platform, so
     `send_template_message` is the only send method here — there is
     deliberately no `send_text`.
  2. Delivery is asynchronous. The API returns a message id, and delivery and
     read receipts arrive later by webhook, which is why `NotificationRecord`
     has SENT and DELIVERED as separate states.

To verify before go-live: which BSP this deployment uses, the template approval
workflow and exact template names, and the webhook signature scheme.
"""

import logging
from typing import Any, Protocol

import httpx

from app.integrations.base import IntegrationNotConfiguredError

logger = logging.getLogger(__name__)


class WhatsAppClient(Protocol):
    """Operations NOVA needs from the WhatsApp Business Platform."""

    async def send_template_message(
        self,
        *,
        to_phone: str,
        template_name: str,
        params: dict[str, str],
        language: str = "ar",
    ) -> str:
        """Sends an approved template. Returns the provider message id."""
        ...


class NotConfiguredWhatsAppClient:
    """Placeholder used until a real BSP integration exists.

    Raises rather than silently succeeding: a notification recorded as SENT
    that never left the building is worse than a visible failure, because the
    salon believes the customer was told.
    """

    async def send_template_message(
        self,
        *,
        to_phone: str,
        template_name: str,
        params: dict[str, str],
        language: str = "ar",
    ) -> str:
        raise IntegrationNotConfiguredError("WhatsApp")


class WhatsAppCloudClient:
    """Live adapter for the Meta Cloud API message shape.

    Most BSPs expose either this shape or a thin wrapper over it. Swapping to a
    different BSP means another class satisfying `WhatsAppClient`, not touching
    the notification module.
    """

    def __init__(
        self,
        *,
        api_key: str,
        phone_number_id: str,
        base_url: str = "https://graph.facebook.com/v21.0",
        timeout_seconds: float = 15.0,
    ) -> None:
        self.api_key = api_key
        self.phone_number_id = phone_number_id
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def send_template_message(
        self,
        *,
        to_phone: str,
        template_name: str,
        params: dict[str, str],
        language: str = "ar",
    ) -> str:
        # Template variables are positional in WhatsApp's API ({{1}}, {{2}}).
        # Sorting by key gives a stable order rather than relying on dict
        # insertion order surviving a round trip through JSONB.
        body: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": params[key]} for key in sorted(params)
                        ],
                    }
                ],
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/{self.phone_number_id}/messages",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
            )
            response.raise_for_status()
            payload = response.json()

        messages = payload.get("messages") or []
        if not messages:
            raise RuntimeError("WhatsApp accepted the request but returned no message id.")
        return str(messages[0]["id"])


def build_whatsapp_client(
    *, api_key: str | None, phone_number_id: str | None, base_url: str | None
) -> WhatsAppClient:
    if not (api_key and phone_number_id):
        return NotConfiguredWhatsAppClient()
    return WhatsAppCloudClient(
        api_key=api_key,
        phone_number_id=phone_number_id,
        base_url=base_url or "https://graph.facebook.com/v21.0",
    )
