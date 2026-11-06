"""ai_agents · tools — customer service: the caller's own bookings and payments,
a cancellation to confirm (never made), and a handoff to a person.

On a phone call (ADR-0017) the caller is only a number, and caller ID can be
forged, so every tool here that reads or offers to change a booking refuses
until the caller proved the customer's phone (`verify_caller`).
"""

from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.ai_agents.service import TenantServices

from app.core.exceptions import NotFoundError
from app.modules.ai_agents.tools.base import (
    PendingCancellation,
    Result,
    ToolkitBase,
    _iso,
    _refuse,
)

_VERIFY_FIRST = (
    "Nothing was read. Call verify_caller first: the caller types the code it sends to their "
    "WhatsApp, and only then can you read or change their bookings."
)


class CustomerServiceTools(ToolkitBase):
    async def _unverified(self, tool_name: str) -> Result | None:
        """The refusal for an unverified caller, or None to go on."""
        if self.deps.caller_verified:
            return None
        return await self._run(tool_name, lambda: _refuse("caller_not_verified", _VERIFY_FIRST))

    async def _callers_booking(
        self, services: "TenantServices", booking_id: UUID, *, for_cancellation: bool = False
    ) -> Any:
        """A booking the caller may see: their principal's guard, and, when staff or
        a phone call act for one named customer, that customer's own booking.

        A service principal sees every booking in the tenant, so without the
        second check a call would reach anyone's booking by its id.
        """
        booking = (
            await services.booking.preview_cancellation(booking_id, self.deps.principal)
            if for_cancellation
            else await services.booking.get_for_principal(booking_id, self.deps.principal)
        )
        if (
            not self.deps.self_service
            and self.deps.customer_id is not None
            and booking.customer_id != self.deps.customer_id
        ):
            raise NotFoundError("Booking not found.")
        return booking

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
            "local_time": self._when(booking.slot.starts_at, location.timezone),
            "starts_at": booking.slot.starts_at.isoformat(),
            "price": str(booking.price.amount),
            "currency": booking.price.currency,
        }

    async def list_my_bookings(self) -> Result:
        """The caller's own recent bookings, newest first."""
        if refusal := await self._unverified("list_my_bookings"):
            return refusal

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
        if refusal := await self._unverified("get_booking_status"):
            return refusal

        async def work(services: "TenantServices") -> Result:
            booking = await self._callers_booking(services, booking_id)
            return await self._booking(services, booking)

        return await self._call("get_booking_status", work)

    async def get_payment_status(self, booking_id: UUID) -> Result:
        """The payments on one of the caller's bookings."""
        if refusal := await self._unverified("get_payment_status"):
            return refusal

        async def work(services: "TenantServices") -> Result:
            await self._callers_booking(services, booking_id)
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
        if refusal := await self._unverified("request_cancellation"):
            return refusal
        pending: list[PendingCancellation] = []

        async def work(services: "TenantServices") -> Result:
            booking = await self._callers_booking(services, booking_id, for_cancellation=True)
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

    async def verify_caller(self) -> Result:
        """Sends the caller a 4-digit code on WhatsApp, to type on the keypad. Needed once
        per call before reading or changing their bookings."""

        async def work() -> Result:
            if self.deps.caller_verified:
                return {"verified": True}
            if self.deps.customer_id is None:
                return {
                    "error": "no_customer_record",
                    "message": "This number has no bookings here. Offer to book one instead.",
                }
            # The call center sends the code after the turn: it owns the call.
            self.deps.artifacts.verification_requested = True
            return {
                "code_sent": True,
                "next_step": "Tell the caller you sent a code to their WhatsApp, and to type "
                "it on the keypad.",
            }

        return await self._call_without_services("verify_caller", work)

    async def escalate_to_human(self, summary: str) -> Result:
        """Hands the conversation to a person, with a short summary of the problem."""

        async def work() -> Result:
            self.deps.artifacts.handoff_reason = summary[:500]
            return {"escalated": True}

        return await self._call_without_services("escalate_to_human", work)
