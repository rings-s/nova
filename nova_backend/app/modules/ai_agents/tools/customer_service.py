"""ai_agents · tools — customer service: the caller's own bookings and payments,
a cancellation to confirm (never made), and a handoff to a person.
"""

from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.ai_agents.service import TenantServices

from app.modules.ai_agents.tools.base import (
    PendingCancellation,
    Result,
    ToolkitBase,
    _iso,
    _local,
)


class CustomerServiceTools(ToolkitBase):
    async def _booking(self, services: "TenantServices", booking: Any) -> Result:
        """A booking in words. No notes and nothing about the customer: this goes
        into a prompt. Names and a local time, not ids: live, a small model read
        raw ids back to the customer."""
        location = await services.catalog.get_location(booking.location_id)
        service = await services.catalog.get_service(booking.service_id)
        return {
            "booking_id": str(booking.id),
            "status": str(booking.status),
            "service": self._name(service),
            "local_time": _local(booking.slot.starts_at, location.timezone),
            "starts_at": booking.slot.starts_at.isoformat(),
            "price": str(booking.price.amount),
            "currency": booking.price.currency,
        }

    async def list_my_bookings(self) -> Result:
        """The caller's own recent bookings, newest first."""

        async def work(services: "TenantServices") -> Result:
            customer_id = self.deps.customer_id
            if customer_id is None:  # pragma: no cover - the router always resolves one
                return {"bookings": []}
            bookings = await services.booking.list_for_customer_reference(
                customer_id, self_service=self.deps.self_service, limit=10
            )
            return {"bookings": [await self._booking(services, b) for b in bookings]}

        return await self._call("list_my_bookings", work)

    async def get_booking_status(self, booking_id: UUID) -> Result:
        """One booking, if the caller may see it. Otherwise "not found"."""

        async def work(services: "TenantServices") -> Result:
            booking = await services.booking.get_for_principal(booking_id, self.deps.principal)
            return await self._booking(services, booking)

        return await self._call("get_booking_status", work)

    async def get_payment_status(self, booking_id: UUID) -> Result:
        """The payments on one of the caller's bookings."""

        async def work(services: "TenantServices") -> Result:
            payments = await services.payment.list_for_booking_for_principal(
                booking_id, self.deps.principal
            )
            return {
                "booking_id": str(booking_id),
                "payments": [
                    {
                        "status": str(p.status),
                        "amount": str(p.amount.amount),
                        "refunded_amount": str(p.refunded_amount),
                        "currency": p.amount.currency,
                        "captured_at": _iso(p.captured_at),
                    }
                    for p in payments
                ],
            }

        return await self._call("get_payment_status", work)

    async def request_cancellation(self, booking_id: UUID, reason: str | None = None) -> Result:
        """Asks the customer to confirm cancelling one of their bookings. Cancels nothing.

        Checks the booking is theirs and could be cancelled now, under the
        business's cancellation policy, then hands it to the client, where the
        customer confirms. An agent that cancelled by itself could be talked
        into it by text the customer never wrote.
        """
        pending: list[PendingCancellation] = []

        async def work(services: "TenantServices") -> Result:
            booking = await services.booking.preview_cancellation(booking_id, self.deps.principal)
            pending.append(
                PendingCancellation(
                    booking_id=booking.id,
                    starts_at=booking.slot.starts_at,
                    reason=reason[:500] if reason else None,
                )
            )
            return {
                "booking_id": str(booking.id),
                "starts_at": booking.slot.starts_at.isoformat(),
                "cancelled": False,
                "awaiting_customer_confirmation": True,
            }

        result = await self._call("request_cancellation", work)
        if "error" not in result:
            self.deps.artifacts.pending_cancellations.extend(pending)
            self.deps.artifacts.booking_ids.append(UUID(result["booking_id"]))
        return result

    async def escalate_to_human(self, summary: str) -> Result:
        """Hands the conversation to a person, with a short summary of the problem."""

        async def work() -> Result:
            self.deps.artifacts.handoff_reason = summary[:500]
            return {"escalated": True}

        return await self._call_without_services("escalate_to_human", work)
