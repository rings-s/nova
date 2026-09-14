"""notification · APPLICATION layer — use cases.

Layer rule: domain, repository, events, integrations, and other modules'
*services*. Must not import fastapi or another module's models/repository.

This context is a CONSUMER. It reacts to domain events — BookingConfirmed,
CustomerCalled, PaymentCaptured — and is never called directly by booking or
queue. If you find yourself importing NotificationService from booking, publish
an event instead (see `app/worker/outbox.py` for where the events land).

Every send passes three gates before a message leaves:

    1. consent      per channel, and separately for marketing (PDPL)
    2. quiet hours  marketing only; a booking confirmation ignores them
    3. dedupe       the outbox delivers at-least-once, so the same event can
                    arrive twice and must not produce two messages
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from app.core.events import publish_event
from app.integrations.whatsapp.client import WhatsAppClient
from app.modules.identity.service import CustomerService
from app.modules.notification.domain import (
    MessageTemplate,
    NotificationChannel,
    NotificationStatus,
    category_for,
    has_consent,
    is_within_quiet_hours,
    next_delivery_attempt_at,
    next_send_time,
    render_template_params,
)
from app.modules.notification.events import NotificationSent, NotificationSuppressed
from app.modules.notification.exceptions import NotificationNotFoundError
from app.modules.notification.models import NotificationRecord
from app.modules.notification.repository import NotificationRepository

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(
        self,
        *,
        repository: NotificationRepository,
        whatsapp: WhatsAppClient,
        customers: CustomerService,
        tenant_id: UUID,
        default_timezone: str = "Asia/Riyadh",
        quiet_hours_start: int = 22,
        quiet_hours_end: int = 8,
    ) -> None:
        self.repository = repository
        self.whatsapp = whatsapp
        self.customers = customers
        self.tenant_id = tenant_id
        self.default_timezone = default_timezone
        self.quiet_hours_start = quiet_hours_start
        self.quiet_hours_end = quiet_hours_end

    @property
    def session(self):
        return self.repository.session

    async def enqueue(
        self,
        *,
        customer_id: UUID,
        template: MessageTemplate,
        context: dict[str, str],
        dedupe_key: str,
        channel: NotificationChannel = NotificationChannel.WHATSAPP,
        timezone: str | None = None,
        now: datetime | None = None,
    ) -> NotificationRecord:
        """Records a message to send, applying consent and quiet-hours rules.

        Returns the existing record unchanged if `dedupe_key` was already used —
        the outbox delivers at-least-once, and a customer receiving "your
        booking is confirmed" twice reads as a system that double-booked them.
        """
        now = now or datetime.now(UTC)

        existing = await self.repository.find_by_dedupe_key(dedupe_key)
        if existing is not None:
            return existing

        customer = await self.customers.get(customer_id)
        category = category_for(template)

        record = NotificationRecord(
            tenant_id=self.tenant_id,
            customer_id=customer_id,
            channel=channel,
            template=template,
            status=NotificationStatus.PENDING,
            payload=render_template_params(template, context),
            dedupe_key=dedupe_key,
            # "Not before now" — i.e. send on the next sweep. Set here rather
            # than after the consent check on purpose: the suppression branch
            # below flushes, and `scheduled_for` is NOT NULL, so a later
            # assignment would fail every suppressed insert. The quiet-hours
            # branch overwrites this when it applies.
            scheduled_for=now,
        )

        if not has_consent(
            channel=channel,
            category=category,
            whatsapp_consent=customer.whatsapp_consent,
            marketing_consent=customer.marketing_consent,
        ):
            # Suppressed, not failed: nothing went wrong, we were simply not
            # permitted to send. Keeping the record is the audit trail proving
            # we honoured the opt-out.
            record.status = NotificationStatus.SUPPRESSED
            record.error = "consent_withheld"
            self.repository.add(record)
            await self.repository.session.flush()

            await publish_event(
                self.session,
                NotificationSuppressed(
                    tenant_id=self.tenant_id,
                    notification_id=record.id,
                    customer_id=customer_id,
                    reason="consent_withheld",
                ),
            )
            return record

        zone = timezone or self.default_timezone
        if category.value == "marketing" and is_within_quiet_hours(
            now,
            timezone=zone,
            start_hour=self.quiet_hours_start,
            end_hour=self.quiet_hours_end,
        ):
            # Held, not dropped. A win-back offer is still worth sending at
            # 08:00 — it is just not worth sending at 02:00.
            record.scheduled_for = next_send_time(now, timezone=zone, end_hour=self.quiet_hours_end)

        self.repository.add(record)
        await self.repository.session.flush()
        return record

    async def deliver(
        self, notification_id: UUID, *, now: datetime | None = None
    ) -> NotificationRecord:
        """Actually sends a pending message.

        Called by the worker rather than inline: a WhatsApp API call inside a
        request would put a third party's latency on the customer's booking.
        """
        now = now or datetime.now(UTC)
        record = await self.repository.get(notification_id)
        if record is None:
            raise NotificationNotFoundError(notification_id)

        if record.status is not NotificationStatus.PENDING:
            return record
        if record.scheduled_for > now:
            return record

        customer = await self.customers.get(record.customer_id)
        record.attempts += 1

        try:
            message_id = await self.whatsapp.send_template_message(
                to_phone=customer.phone,
                template_name=str(record.template),
                params=dict(record.payload),
                language=customer.preferred_language,
            )
        except Exception as exc:
            # A BSP returning 503 for thirty seconds must not cost the customer
            # their booking confirmation. Stay PENDING and come back later,
            # until the attempts are spent — only then is FAILED terminal.
            retry_at = next_delivery_attempt_at(now, attempts=record.attempts)
            record.error = str(exc)[:1000]
            if retry_at is None:
                record.status = NotificationStatus.FAILED
            else:
                record.scheduled_for = retry_at
            await self.repository.session.flush()
            logger.warning(
                "notification_send_failed",
                extra={
                    "notification_id": str(notification_id),
                    "attempts": record.attempts,
                    "retry_at": retry_at.isoformat() if retry_at else None,
                    "terminal": retry_at is None,
                },
                exc_info=True,
            )
            return record

        record.status = NotificationStatus.SENT
        record.provider_message_id = message_id
        record.sent_at = now
        record.error = None
        await self.repository.session.flush()

        await publish_event(
            self.session,
            NotificationSent(
                tenant_id=self.tenant_id,
                notification_id=record.id,
                customer_id=record.customer_id,
                template=str(record.template),
            ),
        )
        return record

    async def mark_delivery_status(
        self, *, provider_message_id: str, status: str
    ) -> NotificationRecord | None:
        """Applies a delivery/read receipt from the BSP webhook."""
        record = await self.repository.find_by_provider_message_id(provider_message_id)
        if record is None:
            return None

        if status == "delivered" and record.status is NotificationStatus.SENT:
            record.status = NotificationStatus.DELIVERED
        elif status == "read" and record.status in (
            NotificationStatus.SENT,
            NotificationStatus.DELIVERED,
        ):
            record.status = NotificationStatus.READ
        elif status == "failed":
            record.status = NotificationStatus.FAILED

        await self.repository.session.flush()
        return record

    async def list_for_customer(
        self, customer_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[NotificationRecord]:
        return await self.repository.list_for_customer(customer_id, limit=limit, offset=offset)

    async def list_due(self, *, now: datetime | None = None, limit: int = 100):
        return await self.repository.list_due(now=now or datetime.now(UTC), limit=limit)


__all__ = ["NotificationService"]
