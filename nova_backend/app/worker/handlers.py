"""What happens when a domain event is delivered.

This is the seam that keeps the modules decoupled. Booking never imports
notification; it publishes `BookingConfirmed` and the subscription below turns
that into a WhatsApp message. Adding a reaction means adding a handler here,
not adding an import to the module that raised the event.

Every handler must be IDEMPOTENT. The outbox delivers at-least-once — a
dispatcher that dies between sending and marking an event published will
redeliver it — so each handler either uses a stable dedupe key or checks
current state before acting.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.dependencies import build_customer_service
from app.modules.notification.dependencies import build_notification_service
from app.modules.notification.domain import MessageTemplate

logger = logging.getLogger(__name__)

#: event name -> handlers. A list, so several contexts can react to one event
#: without knowing about each other.
EventHandler = Callable[[AsyncSession, UUID, dict[str, Any]], Awaitable[None]]
_HANDLERS: dict[str, list[EventHandler]] = {}


def subscribe(event_name: str) -> Callable[[EventHandler], EventHandler]:
    def register(handler: EventHandler) -> EventHandler:
        _HANDLERS.setdefault(event_name, []).append(handler)
        return handler

    return register


def handlers_for(event_name: str) -> list[EventHandler]:
    return _HANDLERS.get(event_name, [])


def _format_time(value: str | None) -> str:
    """Event payloads carry ISO strings; templates want something readable."""
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


async def _notify(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    customer_id: str,
    template: MessageTemplate,
    context: dict[str, str],
    dedupe_key: str,
) -> None:
    """Shared path for every notification-raising handler.

    `dedupe_key` is derived from the event and the template, so a redelivered
    event maps to the same notification row rather than a second message.
    """
    notifications = build_notification_service(session, tenant_id)
    customers = build_customer_service(session, tenant_id)

    customer = await customers.get(UUID(customer_id))
    await notifications.enqueue(
        customer_id=customer.id,
        template=template,
        context={"customer_name": customer.full_name, **context},
        dedupe_key=dedupe_key,
    )


@subscribe("BookingConfirmed")
async def on_booking_confirmed(
    session: AsyncSession, tenant_id: UUID, payload: dict[str, Any]
) -> None:
    await _notify(
        session,
        tenant_id,
        customer_id=payload["customer_id"],
        template=MessageTemplate.BOOKING_CONFIRMED,
        context={
            "service_name": payload.get("service_name", "your appointment"),
            "starts_at": _format_time(payload.get("starts_at")),
        },
        dedupe_key=f"booking_confirmed:{payload['booking_id']}",
    )


@subscribe("BookingCancelled")
async def on_booking_cancelled(
    session: AsyncSession, tenant_id: UUID, payload: dict[str, Any]
) -> None:
    await _notify(
        session,
        tenant_id,
        customer_id=payload["customer_id"],
        template=MessageTemplate.BOOKING_CANCELLED,
        context={"starts_at": _format_time(payload.get("starts_at"))},
        dedupe_key=f"booking_cancelled:{payload['booking_id']}",
    )


@subscribe("BookingRescheduled")
async def on_booking_rescheduled(
    session: AsyncSession, tenant_id: UUID, payload: dict[str, Any]
) -> None:
    await _notify(
        session,
        tenant_id,
        customer_id=payload["customer_id"],
        template=MessageTemplate.BOOKING_RESCHEDULED,
        context={
            "previous_starts_at": _format_time(payload.get("previous_starts_at")),
            "starts_at": _format_time(payload.get("starts_at")),
        },
        # Keyed on the new time as well as the id: rescheduling twice is two
        # events the customer genuinely needs to hear about.
        dedupe_key=f"booking_rescheduled:{payload['booking_id']}:{payload.get('starts_at')}",
    )


@subscribe("CustomerCalled")
async def on_customer_called(
    session: AsyncSession, tenant_id: UUID, payload: dict[str, Any]
) -> None:
    """The one queue event a customer genuinely wants pushed to their phone."""
    await _notify(
        session,
        tenant_id,
        customer_id=payload["customer_id"],
        template=MessageTemplate.QUEUE_CALLED,
        context={},
        dedupe_key=f"queue_called:{payload['entry_id']}",
    )


@subscribe("QueueEntryJoined")
async def on_queue_joined(session: AsyncSession, tenant_id: UUID, payload: dict[str, Any]) -> None:
    await _notify(
        session,
        tenant_id,
        customer_id=payload["customer_id"],
        template=MessageTemplate.QUEUE_JOINED,
        context={"position": str(payload.get("position", ""))},
        dedupe_key=f"queue_joined:{payload['entry_id']}",
    )


@subscribe("BookingCompleted")
async def on_booking_completed(
    session: AsyncSession, tenant_id: UUID, payload: dict[str, Any]
) -> None:
    """Accrues commission (docs/11 section 7 step 1).

    Commission accrues on COMPLETED and nowhere else — docs/11 section 3 rule
    5. Subscribing here rather than calling billing from `BookingService` is
    what keeps booking ignorant of money: booking states a fact, billing prices
    it.

    Idempotent through `BillingService.accrue_for_booking`, which returns None
    when a line for this booking already exists. The outbox delivers
    at-least-once, and billing a salon twice for one appointment is the worst
    bug this system could have.
    """
    from app.modules.billing.dependencies import build_billing_service
    from app.modules.booking.dependencies import build_booking_service

    bookings = build_booking_service(session, tenant_id)
    billing = build_billing_service(session, tenant_id)

    booking = await bookings.get(UUID(payload["booking_id"]))
    await billing.accrue_for_booking(
        booking_id=booking.id,
        business_id=booking.business_id,
        customer_id=booking.customer_id,
        source=str(booking.source),
        price=booking.price,
    )


@subscribe("PaymentRefunded")
async def on_payment_refunded(
    session: AsyncSession, tenant_id: UUID, payload: dict[str, Any]
) -> None:
    """Reverses commission (docs/11 section 3 rule 6).

    Writes an offsetting line rather than editing the original, and hands the
    customer's "new" claim back so a refunded introduction can still be billed
    if they book again. Idempotent: a redelivered refund finds the original
    already reversed and does nothing.
    """
    booking_id = payload.get("booking_id")
    if not booking_id:
        # A refund against a payment with no booking — nothing was ever
        # accrued for it.
        return

    from app.modules.billing.dependencies import build_billing_service

    billing = build_billing_service(session, tenant_id)
    await billing.reverse_for_booking(booking_id=UUID(booking_id))


@subscribe("PaymentCaptured")
async def on_payment_captured(
    session: AsyncSession, tenant_id: UUID, payload: dict[str, Any]
) -> None:
    """Receipt. Skipped when the payment was not tied to a booking, since we
    have no customer to send it to."""
    booking_id = payload.get("booking_id")
    if not booking_id:
        return

    from app.modules.booking.dependencies import build_booking_service

    bookings = build_booking_service(session, tenant_id)
    booking = await bookings.get(UUID(booking_id))

    await _notify(
        session,
        tenant_id,
        customer_id=str(booking.customer_id),
        template=MessageTemplate.PAYMENT_RECEIPT,
        context={
            "amount": str(payload.get("amount", "")),
            "currency": str(payload.get("currency", "SAR")),
        },
        dedupe_key=f"payment_receipt:{payload['payment_id']}",
    )


__all__ = ["EventHandler", "handlers_for", "subscribe"]
