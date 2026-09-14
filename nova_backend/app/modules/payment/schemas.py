"""payment · CONTRACT layer — API boundary DTOs.

Layer rule: pydantic only. These are not the domain model and not the table.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import Field

from app.core.schemas import ApiSchema
from app.modules.payment.domain import PaymentStatus


class CreatePaymentIntentRequest(ApiSchema):
    booking_id: UUID
    return_url: str = Field(max_length=2000)
    metadata: dict[str, str] | None = None

    #: Staff override only. Left unset, the amount comes from the booking's own
    #: price and the tenant's deposit policy — a client must not get to decide
    #: what it owes.
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class PaymentOut(ApiSchema):
    id: UUID
    booking_id: UUID | None
    amount: Decimal
    currency: str
    status: PaymentStatus
    gateway: str
    gateway_payment_id: str | None
    webhook_verified: bool
    refunded_amount: Decimal
    failure_code: str | None
    captured_at: datetime | None
    created_at: datetime


class PaymentIntentOut(ApiSchema):
    payment: PaymentOut
    #: Where to send the customer to actually pay. Null when the gateway is
    #: not configured or returned no hosted page.
    redirect_url: str | None


class RefundPaymentRequest(ApiSchema):
    #: Omit to refund everything still refundable.
    amount: Decimal | None = Field(default=None, gt=0)
    reason: str | None = Field(default=None, max_length=500)


class MoyasarWebhookPayload(ApiSchema):
    """Untrusted until the signature is verified (docs/07 section 8).

    Loosely typed on purpose: rejecting a real webhook because the gateway
    added a field would make Moyasar retry a payment we have already taken.
    Validation happens against the signature and our own records, not the shape.
    """

    id: str | None = None
    type: str | None = None
    event: str | None = None
    secret_token: str | None = None
    data: dict[str, Any] | None = None


class WebhookAckOut(ApiSchema):
    """What the gateway gets back.

    Always 200 with a status word once the signature verifies: a non-2xx makes
    Moyasar retry, and retrying is pointless for an event we have already
    processed or will never understand.
    """

    status: str
