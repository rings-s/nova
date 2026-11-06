"""support · APPLICATION layer — opening and resolving follow-ups.

Layer rule: domain, repository, models, events. No fastapi.
Services flush, never commit — the caller owns the transaction boundary.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.core.events import publish_event
from app.core.security import Principal
from app.modules.identity.service import CustomerService
from app.modules.support.domain import (
    FollowUpReason,
    FollowUpSource,
    FollowUpStatus,
    chat_reference,
    clip_text,
)
from app.modules.support.events import FollowUpOpened
from app.modules.support.exceptions import FollowUpNotFoundError
from app.modules.support.models import FollowUp
from app.modules.support.repository import FollowUpRepository


@dataclass(frozen=True)
class FollowUpContact:
    """How staff reach the person: their customer record here, or what they gave."""

    customer_id: UUID | None = None
    name: str | None = None
    phone: str | None = None
    email: str | None = None


class SupportService:
    def __init__(
        self,
        repository: FollowUpRepository,
        customers: CustomerService,
        tenant_id: UUID,
    ) -> None:
        self.repository = repository
        self.customers = customers
        self.tenant_id = tenant_id

    async def open_for_chat(
        self,
        user_id: UUID,
        business_id: UUID | None,
        session_id: str,
        reason: FollowUpReason,
        summary: str | None = None,
        customer_message: str | None = None,
        booking_id: UUID | None = None,
        now: datetime | None = None,
    ) -> UUID:
        """A signed-in customer's conversation handed off: one follow-up per conversation."""
        return await self._open(
            source=FollowUpSource.CHAT,
            source_ref=chat_reference(user_id, business_id, session_id),
            reason=reason,
            business_id=business_id,
            contact=await self._contact_for_user(user_id),
            summary=summary,
            customer_message=customer_message,
            booking_id=booking_id,
            now=now,
        )

    async def open_for_call(
        self,
        call_id: UUID,
        business_id: UUID,
        customer_id: UUID | None,
        caller_phone: str | None,
        reason: FollowUpReason,
        summary: str | None = None,
        customer_message: str | None = None,
        booking_id: UUID | None = None,
        now: datetime | None = None,
    ) -> UUID:
        """Sara promised a call back: one follow-up per call, ringing the number that called."""
        contact = FollowUpContact(phone=caller_phone)
        if customer_id is not None:
            customer = await self.customers.get(customer_id)
            contact = FollowUpContact(
                customer_id=customer.id,
                name=customer.full_name,
                phone=caller_phone or customer.phone,
                email=customer.email,
            )
        return await self._open(
            source=FollowUpSource.CALL,
            source_ref=str(call_id),
            reason=reason,
            business_id=business_id,
            contact=contact,
            summary=summary,
            customer_message=customer_message,
            booking_id=booking_id,
            now=now,
        )

    async def list(
        self, *, status: FollowUpStatus | None = None, limit: int = 50, offset: int = 0
    ) -> list[FollowUp]:
        """Newest first. Staff only: a follow-up holds a customer's contact and words."""
        return await self.repository.list_by_status(status, limit=limit, offset=offset)

    async def count_open(self) -> int:
        return await self.repository.count_open()

    async def resolve(
        self, follow_up_id: UUID, principal: Principal, *, now: datetime | None = None
    ) -> FollowUp:
        """Marks it done. Resolving one already resolved changes nothing."""
        follow_up = await self.repository.get(follow_up_id)
        if follow_up is None:
            raise FollowUpNotFoundError(follow_up_id)
        if follow_up.status is not FollowUpStatus.RESOLVED:
            follow_up.status = FollowUpStatus.RESOLVED
            follow_up.resolved_at = now or datetime.now(UTC)
            follow_up.resolved_by = principal.subject_id
            await self.repository.session.flush()
        return follow_up

    async def _contact_for_user(self, user_id: UUID) -> FollowUpContact:
        customer = await self.customers.find_for_user(user_id)
        if customer is not None:
            return FollowUpContact(
                customer_id=customer.id,
                name=customer.full_name,
                phone=customer.phone,
                email=customer.email,
            )
        account = await self.customers.account_contact(user_id)
        if account is None:
            return FollowUpContact()
        name, phone, email = account
        return FollowUpContact(name=name, phone=phone, email=email)

    async def _open(
        self,
        source: FollowUpSource,
        source_ref: str,
        reason: FollowUpReason,
        business_id: UUID | None,
        contact: FollowUpContact,
        summary: str | None,
        customer_message: str | None,
        booking_id: UUID | None,
        now: datetime | None,
    ) -> UUID:
        follow_up_id, newly_open = await self.repository.open(
            values={
                "source": source,
                "source_ref": source_ref,
                "reason": reason,
                "business_id": business_id,
                "customer_id": contact.customer_id,
                "booking_id": booking_id,
                "contact_name": contact.name,
                "contact_phone": contact.phone,
                "contact_email": contact.email,
                "summary": clip_text(summary),
                "customer_message": clip_text(customer_message),
            },
            now=now or datetime.now(UTC),
        )
        if newly_open:
            await publish_event(
                self.repository.session,
                FollowUpOpened(
                    tenant_id=self.tenant_id,
                    follow_up_id=follow_up_id,
                    business_id=business_id,
                    source=str(source),
                    reason=str(reason),
                ),
            )
        return follow_up_id
