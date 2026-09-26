"""ai_agents · the tools — thin wrappers over application services (docs/13 section 4).

Every tool is a translation: arguments in, one service call, a small JSON-able
dict out. There is no business logic here. A rule implemented in a tool would
be a rule the AI path enforces and the HTTP path does not.

Four things happen around every call, in `_run`:

  1. the allowlist is checked again. The runtime only registers allowed tools,
     so this catches a wiring mistake;
  2. the call is time-boxed (docs/10 section 12);
  3. a domain error becomes a refusal the model can relay, instead of ending
     the turn (docs/13 section 11);
  4. every number in the result is recorded as grounded for this turn, and the
     call is logged with session, tenant, tool and outcome (docs/10 section 2).

A tool that needs a service opens its own unit of work (`AgentDeps.services`):
a short transaction scoped to the tenant, committed when the tool returns and
rolled back when it raises or times out. Nothing holds a connection, or the
advisory lock a hold or a queue join takes, while the model thinks — and a
write is real the moment its tool returns. What a write produced for the client
(a hold and its token, a place in a queue) is recorded in `TurnArtifacts` only
after that commit.

Customer-facing tools act only on what the caller could reach over HTTP: each
one that names a booking, payment or queue entry runs the same per-row guard its
route runs. Owner-facing tools work on the one business the request named.
"""

import asyncio
import json
import logging
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, fields
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.modules.ai_agents.agents import WRITE_TOOLS, AgentSpec
from app.modules.ai_agents.guardrails import (
    GuardrailError,
    GuardrailViolation,
    ProposalTarget,
    ProposedAction,
    ProposedActionKind,
    assert_tool_allowed,
    check_proposal,
    find_ungrounded_numbers,
    grounded_values_in_result,
)
from app.modules.analytics.domain import CHARTS, ChartId, Dimension, ForecastMetric, Granularity

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.ai_agents.service import AgentDeps, ServiceScope, TenantServices
    from app.modules.discovery.service import DiscoveryService

logger = logging.getLogger(__name__)

Result = dict[str, Any]
#: A tool's body, given the services of the unit of work it runs in.
Work = Callable[["TenantServices"], Awaitable[Result]]
#: A marketplace tool's body, given the discovery service of its unit of work.
DiscoveryWork = Callable[["DiscoveryService"], Awaitable[Result]]

#: How many free times a search returns. More is noise to a small model and a
#: long list to the customer; "later" is one more question away.
_MAX_TIMES = 6
#: Offered times start at least this far ahead. A turn can take minutes on a
#: small local model, and a time that starts before the customer's "yes"
#: arrives cannot be booked.
_MIN_LEAD = timedelta(minutes=30)


@dataclass(frozen=True)
class HeldSlot:
    """A slot a tool held and showed the customer: an *offer*.

    The client may book it with `hold_token`; `book_held_slot` books it for the
    customer once they say yes in a later turn. `tenant_id` and `business_slug`
    say where, because the marketplace assistant holds across businesses.
    """

    hold_token: str
    location_id: UUID
    provider_id: UUID
    service_id: UUID
    starts_at: datetime
    ends_at: datetime
    expires_at: datetime
    tenant_id: UUID | None = None
    business_slug: str | None = None
    #: "Classic Manicure at Lumière Spa, Thu 24 Sep 2026, 09:45 (Asia/Riyadh)":
    #: what the customer is told is held, whatever the model writes.
    label: str | None = None


def encode_offers(offers: list[HeldSlot]) -> bytes:
    """Offers as JSON for conversation memory (`history.py`)."""
    return json.dumps(
        [{f.name: _json(getattr(offer, f.name)) for f in fields(HeldSlot)} for offer in offers]
    ).encode()


def decode_offers(data: bytes | None) -> list[HeldSlot]:
    """The inverse of `encode_offers`; anything unreadable is simply forgotten."""
    if not data:
        return []
    try:
        rows = json.loads(data)
        return [
            HeldSlot(
                hold_token=row["hold_token"],
                location_id=UUID(row["location_id"]),
                provider_id=UUID(row["provider_id"]),
                service_id=UUID(row["service_id"]),
                starts_at=datetime.fromisoformat(row["starts_at"]),
                ends_at=datetime.fromisoformat(row["ends_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                tenant_id=UUID(row["tenant_id"]) if row.get("tenant_id") else None,
                business_slug=row.get("business_slug"),
                label=row.get("label"),
            )
            for row in rows
        ]
    except (ValueError, KeyError, TypeError):
        logger.warning("ai_offers_unreadable")
        return []


def _json(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


@dataclass(frozen=True)
class BookedTicket:
    """A booking an agent made this turn, with its QR ticket for the customer.

    `qr_payload` is the customer's check-in credential. It goes to the client
    only: never to the model, the logs or conversation memory.
    """

    booking_id: UUID
    tenant_id: UUID
    business_name: str
    booking_status: str
    starts_at: datetime
    ends_at: datetime
    ticket_id: UUID
    ticket_code: str
    qr_payload: str
    expires_at: datetime
    ticket_page_url: str


@dataclass(frozen=True)
class QueuePlace:
    """A place a tool took in a walk-in queue this turn."""

    entry_id: UUID
    queue_id: UUID
    place_in_line: int
    estimated_wait_minutes: int | None


@dataclass(frozen=True)
class PendingCancellation:
    """A booking the customer asked to cancel, waiting for them to confirm it.

    The agent never cancels. The client shows this and, if the customer agrees,
    calls `POST /tenants/{tenant_id}/bookings/{booking_id}/cancel` itself.
    """

    booking_id: UUID
    starts_at: datetime
    reason: str | None


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text(value: Any) -> Any:
    return str(value) if isinstance(value, Decimal) else value


#: Longest tenant-written text (a name, a title, a city) a tool hands the model.
#: The marketplace agent shows one business's words to another's customers, with
#: booking tools attached: long enough for any real name, too short for a
#: paragraph of instructions.
MAX_SHOWN_TEXT = 80


def _shown(value: str | None) -> str | None:
    """Tenant-written text as the model sees it: one line, without control or
    invisible format characters, at most `MAX_SHOWN_TEXT` characters."""
    if value is None:
        return None
    # Format characters (zero-width, bidi overrides) are dropped; line breaks and
    # other controls or separators become a space.
    kept = "".join(
        " " if unicodedata.category(c)[0] in "CZ" else c
        for c in value
        if unicodedata.category(c) != "Cf"
    )
    line = " ".join(kept.split())
    if len(line) > MAX_SHOWN_TEXT:
        return line[: MAX_SHOWN_TEXT - 1].rstrip() + "…"
    return line


def _held(
    hold: Any, *, tenant_id: UUID | None, slug: str | None = None, label: str | None = None
) -> HeldSlot:
    return HeldSlot(
        hold_token=hold.hold_token,
        location_id=hold.location_id,
        provider_id=hold.provider_id,
        service_id=hold.service_id,
        starts_at=hold.starts_at,
        ends_at=hold.ends_at,
        expires_at=hold.expires_at,
        tenant_id=tenant_id,
        business_slug=slug,
        label=label,
    )


def _same_instant(a: datetime, b: datetime) -> bool:
    """Equal to the minute. A model may drop seconds or restate the offset."""
    if a.tzinfo is None:
        a = a.replace(tzinfo=UTC)
    if b.tzinfo is None:
        b = b.replace(tzinfo=UTC)
    return abs((a - b).total_seconds()) < 60


class AgentToolkit:
    def __init__(self, deps: "AgentDeps", *, spec: AgentSpec, tool_timeout_seconds: float) -> None:
        self.deps = deps
        self.spec = spec
        self.tool_timeout_seconds = tool_timeout_seconds

    def for_agent(self) -> list[Callable[..., Awaitable[Result]]]:
        """Only this agent's tools. An unlisted tool never reaches the model."""
        return [getattr(self, name) for name in sorted(self.spec.tools)]

    async def _call(self, tool_name: str, work: Work) -> Result:
        """Runs a tool inside a unit of work of its own."""

        return await self._call_in(tool_name, self._tenant_scope(self.deps.tenant_id), work)

    async def _call_in(self, tool_name: str, scope: "ServiceScope", work: Work) -> Result:
        """Runs a tool in a unit of work of `scope`'s tenant."""

        async def in_unit_of_work() -> Result:
            async with scope() as services:
                return await work(services)

        return await self._run(tool_name, in_unit_of_work)

    async def _call_discovery(self, tool_name: str, work: DiscoveryWork) -> Result:
        """Runs a marketplace tool in a unit of work of the public listing window."""
        discovery = self.deps.discovery
        if discovery is None:  # pragma: no cover - only marketplace agents hold these tools
            raise NotFoundError("The marketplace is not available here.")

        async def in_unit_of_work() -> Result:
            async with discovery() as service:
                return await work(service)

        return await self._run(tool_name, in_unit_of_work)

    def _tenant_scope(self, tenant_id: UUID | None) -> "ServiceScope":
        """The unit of work for one tenant: the turn's own, or one the
        marketplace resolved from a listing.

        A listing names its tenant, never the model, and the caller must be
        allowed to act there: a customer may reach any tenant on the marketplace,
        exactly as over HTTP.
        """
        if tenant_id is not None and tenant_id == self.deps.tenant_id and self.deps.services:
            return self.deps.services
        if tenant_id is None or self.deps.services_for is None:  # pragma: no cover
            raise NotFoundError("This agent works on one business.")
        if not self.deps.principal.can_access_tenant(tenant_id):
            raise GuardrailError(
                GuardrailViolation.TENANT_MISMATCH, "You do not have access to that business."
            )
        return self.deps.services_for(tenant_id)

    async def _call_without_services(
        self, tool_name: str, work: Callable[[], Awaitable[Result]]
    ) -> Result:
        """Runs a tool that needs no service, so opens no transaction."""
        return await self._run(tool_name, work)

    async def _run(self, tool_name: str, work: Callable[[], Awaitable[Result]]) -> Result:
        assert_tool_allowed(tool_name, self.spec.tools)
        try:
            result = await asyncio.wait_for(work(), timeout=self.tool_timeout_seconds)
        except TimeoutError:
            logger.warning("ai_tool_timeout", extra={"agent": self.spec.name, "tool": tool_name})
            raise
        except GuardrailError:
            raise
        except DomainError as exc:
            result = {"error": exc.code, "message": exc.message}
        else:
            if tool_name in WRITE_TOOLS:
                # Its unit of work has committed: whatever the model does next,
                # this happened.
                self.deps.artifacts.committed_writes.append(tool_name)

        self.deps.artifacts.grounded_values |= grounded_values_in_result(result)
        logger.info(
            "ai_tool_called",
            extra={
                "session_id": self.deps.session_id,
                "tenant_id": str(self.deps.tenant_id),
                "agent": self.spec.name,
                "tool": tool_name,
                "outcome": "refused" if "error" in result else "ok",
            },
        )
        return result

    def _business(self) -> UUID:
        business_id = self.deps.business_id
        if business_id is None:  # pragma: no cover - the service refuses this first
            raise NotFoundError("This agent needs a business to work on.")
        return business_id

    def _name(self, record: Any) -> str:
        return _shown(record.name_ar if self.deps.locale == "ar" else record.name_en) or ""

    # --- receptionist -----------------------------------------------------------

    async def search_services(self, location_id: UUID | None = None) -> Result:
        """The services this business sells, with duration and price. location_id is
        optional: without it, every branch's services are listed."""

        async def work(services: "TenantServices") -> Result:
            branch_ids: list[UUID] = []
            if location_id is not None:
                try:
                    branch_ids = [(await services.catalog.get_location(location_id)).id]
                except NotFoundError:
                    # Live, a small model guessed a branch id instead of asking
                    # list_branches. The storefront's branches are the answer.
                    branch_ids = []
            if not branch_ids:
                branch_ids = [branch.id for branch in await self._branches(services)]
            offered = []
            for branch_id in branch_ids:
                offered.extend(await services.catalog.list_services(branch_id))
            return {
                "services": [
                    {
                        "service_id": str(s.id),
                        "name": self._name(s),
                        "duration_minutes": s.duration_minutes,
                        "price": str(s.price),
                        "currency": s.currency,
                    }
                    for s in offered
                    if s.is_active
                ][:20]
            }

        return await self._call("search_services", work)

    async def get_provider_info(self, provider_id: UUID) -> Result:
        """A provider's name and title."""

        async def work(services: "TenantServices") -> Result:
            provider = await services.catalog.get_provider(provider_id)
            title = provider.title_ar if self.deps.locale == "ar" else provider.title_en
            return {
                "provider_id": str(provider.id),
                "name": self._name(provider),
                "title": _shown(title),
            }

        return await self._call("get_provider_info", work)

    async def get_available_slots(
        self, provider_id: UUID, service_id: UUID, days_ahead: int = 7
    ) -> Result:
        """Real bookable start times, generated by the booking domain (docs/07 section 5)."""

        async def work(services: "TenantServices") -> Result:
            now = datetime.now(UTC)
            slots = await services.booking.availability(
                provider_id=provider_id,
                service_id=service_id,
                date_from=now,
                date_to=now + timedelta(days=max(1, min(days_ahead, 30))),
            )
            return {
                "available": len(slots),
                "starts_at": [slot.starts_at.isoformat() for slot in slots[:20]],
            }

        return await self._call("get_available_slots", work)

    async def hold_slot(
        self, service_id: str, starts_at: datetime, provider_id: UUID | None = None
    ) -> Result:
        """Holds a free time for the customer to confirm, once they asked to book it.

        Pass service_id and a starts_at that find_available_times returned. provider_id is
        optional: any qualified provider free then is chosen.
        """
        if self.deps.artifacts.held_slots:
            # One hold per reply. Live, a small model held a time and then kept
            # holding others instead of answering; each refusal cost a minute.
            return await self._run("hold_slot", _already_holding)
        held: list[HeldSlot] = []

        async def work(services: "TenantServices") -> Result:
            service = await self._service_ref(services, service_id)
            chosen = await self._free_provider(services, service.id, starts_at, provider_id)
            hold = await services.booking.hold_slot(
                provider_id=chosen,
                service_id=service.id,
                starts_at=starts_at,
                principal=self.deps.principal,
                customer_id=self.deps.customer_id,
            )
            # No token here. It is a bearer credential for the slot, the
            # response hands it to the client, and the model has no use for it:
            # the prompt, the logs and conversation memory are no place for it.
            details = await self._hold_details(services, hold)
            held.append(_held(hold, tenant_id=self.deps.tenant_id, label=details["label"]))
            return {
                "held": True,
                "starts_at": hold.starts_at.isoformat(),
                **{k: v for k, v in details.items() if k != "label"},
                "expires_at": hold.expires_at.isoformat(),
                "next_step": _ASK_TO_CONFIRM,
            }

        result = await self._call("hold_slot", work)
        if "error" not in result:
            # Recorded only now that the unit of work has committed.
            self.deps.artifacts.held_slots.extend(held)
        return result

    async def list_branches(self) -> Result:
        """This business's branches: where the customer can be seen."""

        async def work(services: "TenantServices") -> Result:
            return {
                "branches": [
                    {
                        "location_id": str(location.id),
                        "name": self._name(location),
                        "city": _shown(location.city),
                    }
                    for location in await self._branches(services)
                ]
            }

        return await self._call("list_branches", work)

    async def _branches(
        self, services: "TenantServices", business_id: UUID | None = None
    ) -> list[Any]:
        """A business's branches: the one named, the storefront's, or this tenant's."""
        business_id = business_id or self.deps.business_id
        if business_id is not None:
            business_ids = [business_id]
        else:
            business_ids = [b.id for b in await services.catalog.list_businesses(limit=5)]
        branches: list[Any] = []
        for business_id in business_ids:
            branches.extend(await services.catalog.list_locations(business_id))
        return branches

    async def find_available_times(self, service_id: str, days_ahead: int = 7) -> Result:
        """Free start times for a service across every provider who performs it.
        service_id is the service's id, or its name ("Classic Manicure")."""

        async def work(services: "TenantServices") -> Result:
            service = await self._service_ref(services, service_id)
            return await self._times_for_service(services, service.id, days_ahead)

        return await self._call("find_available_times", work)

    async def _service_ref(
        self, services: "TenantServices", ref: str | UUID, business_id: UUID | None = None
    ) -> Any:
        """The business's service a model named, by id or by name.

        Live, qwen3-1.7b invented service ids. A name is what the customer said
        and what the model can repeat, so both resolve, and only among this
        business's own active services. An unknown one is refused with the list.
        """
        offered = [
            service
            for branch in await self._branches(services, business_id)
            for service in await services.catalog.list_services(branch.id)
            if service.is_active
        ]
        text = str(ref).strip()
        for service in offered:
            if str(service.id) == text:
                return service
        wanted = _fold(text)
        names = [(service, _fold(service.name_en), _fold(service.name_ar)) for service in offered]
        exact = [service for service, en, ar in names if wanted in (en, ar)]
        close = [
            service
            for service, en, ar in names
            if wanted and (wanted in en or wanted in ar or (en and en in wanted))
        ]
        if exact or close:
            return (exact or close)[0]
        listed = "; ".join(f"{self._name(s)} (service_id {s.id})" for s in offered[:12])
        raise NotFoundError(f"This business has no such service. It offers: {listed}.")

    async def _times_for_service(
        self,
        services: "TenantServices",
        service_id: UUID,
        days_ahead: int,
        limit: int | None = _MAX_TIMES,
    ) -> Result:
        """The booking domain's slots, merged across qualified providers."""
        service = await services.catalog.get_service(service_id)
        location = await services.catalog.get_location(service.location_id)
        now = datetime.now(UTC)
        earliest = now + _MIN_LEAD
        date_to = now + timedelta(days=max(1, min(days_ahead, 14)))
        offered: list[tuple[datetime, Any]] = []
        for provider in await services.catalog.list_providers(service.location_id):
            if not provider.is_active or not await services.catalog.is_provider_qualified(
                provider.id, service_id
            ):
                continue
            for slot in await services.booking.availability(
                provider_id=provider.id, service_id=service_id, date_from=now, date_to=date_to
            ):
                if slot.starts_at >= earliest:
                    offered.append((slot.starts_at, provider))
        offered.sort(key=lambda pair: (pair[0], str(pair[1].id)))
        return {
            "service": self._name(service),
            "price": str(service.price),
            "currency": service.currency,
            "duration_minutes": service.duration_minutes,
            "available": len(offered),
            "timezone": location.timezone,
            "times": [
                {
                    "starts_at": starts_at.isoformat(),
                    "local_time": _local(starts_at, location.timezone),
                    "provider_id": str(provider.id),
                    "provider": self._name(provider),
                }
                for starts_at, provider in offered[:limit]
            ],
        }

    async def _hold_details(self, services: "TenantServices", hold: Any) -> dict[str, str]:
        """Where and when a hold is, in words, for the model and for the reply."""
        location = await services.catalog.get_location(hold.location_id)
        business = self._name(await services.catalog.get_business(location.business_id))
        service = self._name(await services.catalog.get_service(hold.service_id))
        local_time = _local(hold.starts_at, location.timezone)
        return {
            "local_time": local_time,
            "business": business,
            "service": service,
            "label": f"{service} at {business}, {local_time}",
        }

    async def _free_provider(
        self,
        services: "TenantServices",
        service_id: UUID,
        starts_at: datetime,
        provider_id: UUID | None,
    ) -> UUID:
        """A qualified provider free at `starts_at`: the one named, if it is, else any.

        A small model names the wrong id (live: the service id as provider_id) or
        guesses a time. Rather than refuse the id, pick a provider who is free;
        rather than refuse the time bare, say which times are free.
        """
        found = await self._times_for_service(services, service_id, days_ahead=14, limit=None)
        free = [
            t
            for t in found["times"]
            if _same_instant(datetime.fromisoformat(t["starts_at"]), starts_at)
        ]
        if free:
            named = [t for t in free if t["provider_id"] == str(provider_id)]
            return UUID((named or free)[0]["provider_id"])
        upcoming = "; ".join(
            f"{t['local_time']} (starts_at {t['starts_at']})" for t in found["times"][:5]
        )
        raise _TimeNotFree(
            f"That time is not free. Free times: {upcoming}."
            if upcoming
            else "That time is not free, and nothing is free in the next two weeks."
        )

    async def book_held_slot(self, starts_at: datetime) -> Result:
        """Books a time held for the customer in an EARLIER message, once they pressed
        "Yes, book it" on it.

        Issues their QR check-in ticket too. A time held in this same reply cannot
        be booked yet, and neither can one the customer only agreed to in words:
        the model's reading of "yes" is exactly what text in a listing or a
        message could fake, so the confirmation comes from the client's button.
        """
        offer = next((o for o in self.deps.offers if _same_instant(o.starts_at, starts_at)), None)
        if offer is None:
            held_now = any(
                _same_instant(h.starts_at, starts_at) for h in self.deps.artifacts.held_slots
            )
            self.deps.artifacts.booking_failures.append(
                ("not_confirmed_yet", "")
                if held_now
                else ("not_offered", "that time was not held for you")
            )
            return await self._run(
                "book_held_slot",
                lambda: _refuse(
                    "not_confirmed_yet" if held_now else "not_offered",
                    "STOP: do not call book_held_slot again in this reply. " + _ASK_TO_CONFIRM
                    if held_now
                    else "That time was not held for this customer. Hold it with a hold tool, "
                    "show it to them, and book it after they confirm.",
                ),
            )
        if offer.hold_token != self.deps.confirmed_hold_token:
            self.deps.artifacts.booking_failures.append(("not_confirmed", ""))
            return await self._run(
                "book_held_slot",
                lambda: _refuse(
                    "not_confirmed",
                    "STOP: nothing was booked. The customer has not confirmed this time. "
                    'Tell them to press "Yes, book it" under it.',
                ),
            )
        booked: list[BookedTicket] = []

        async def referral() -> str | None:
            # A marketplace offer attributes to the marketplace, recorded the same
            # way a storefront visit records it (ADR-0010).
            if offer.business_slug is None or self.deps.discovery is None:
                return self.deps.referral_token
            try:
                async with self.deps.discovery() as discovery:
                    issued = await discovery.record_referral(offer.business_slug)
            except DomainError:
                # An unlisted business still books; it is simply not attributed.
                return None
            return issued.token

        async def work(services: "TenantServices") -> Result:
            customer_id = self.deps.customer_id
            if customer_id is None:  # pragma: no cover - the router always resolves one
                raise NotFoundError("There is no customer to book for.")
            now = datetime.now(UTC)
            booking = await services.booking.create(
                location_id=offer.location_id,
                service_id=offer.service_id,
                provider_id=offer.provider_id,
                customer_reference_id=customer_id,
                self_service=self.deps.self_service,
                starts_at=offer.starts_at,
                referral_token=referral_token,
                # An expired hold no longer reserves the time; booking without it
                # still succeeds while the time is free, and says so when not.
                hold_token=offer.hold_token if offer.expires_at > now else None,
            )
            issued = await services.queue.issue_ticket(booking_id=booking.id)
            business = await services.catalog.get_business(booking.business_id)
            booked.append(
                BookedTicket(
                    booking_id=booking.id,
                    tenant_id=booking.tenant_id,
                    business_name=self._name(business),
                    booking_status=str(booking.status),
                    starts_at=booking.slot.starts_at,
                    ends_at=booking.slot.ends_at,
                    ticket_id=issued.ticket.id,
                    ticket_code=issued.ticket.ticket_code,
                    qr_payload=issued.qr_payload,
                    expires_at=issued.ticket.expires_at,
                    ticket_page_url=issued.ticket_page_url,
                )
            )
            # The QR payload is the customer's credential: the client gets it,
            # the model does not.
            return {
                "booked": True,
                "booking_status": str(booking.status),
                "starts_at": booking.slot.starts_at.isoformat(),
                "ticket_code": issued.ticket.ticket_code,
                "business": self._name(business),
            }

        referral_token = await referral()
        scope = self._tenant_scope(offer.tenant_id or self.deps.tenant_id)
        result = await self._call_in("book_held_slot", scope, work)
        if "error" in result:
            # Kept for the service: a model may still tell the customer it booked.
            self.deps.artifacts.booking_failures.append(
                (str(result["error"]), str(result.get("message", "")))
            )
        else:
            # Recorded only now that the unit of work has committed.
            self.deps.artifacts.tickets.extend(booked)
            self.deps.artifacts.booking_ids.extend(t.booking_id for t in booked)
            self.deps.artifacts.used_offers.add(offer.hold_token)
        return result

    # --- marketplace ------------------------------------------------------------

    async def search_businesses(
        self, query: str | None = None, city: str | None = None, category: str | None = None
    ) -> Result:
        """Listed businesses (salon, spa, massage, nails, barber…) by name, service, city
        or category, best rated first."""

        term, where, kind = _given(query), _given(city), _given(category)

        async def work(discovery: "DiscoveryService") -> Result:
            cards = await discovery.search(
                term=term, city=where, category=kind, sort="rating", limit=8
            )
            widened = False
            if not cards and (where or kind) and term:
                # A small model fills optional filters it was never told
                # ("city": "unknown"). Rather than report nothing, drop them.
                cards = await discovery.search(term=term, sort="rating", limit=8)
                widened = bool(cards)
            seen: set[str] = set()
            found = []
            for card in cards:
                business = card.business
                if business.slug in seen:
                    continue
                seen.add(business.slug)
                found.append(
                    {
                        "business_slug": business.slug,
                        "name": self._name(business),
                        "branch": self._name(card.location),
                        "city": _shown(card.location.city),
                        "rating_count": business.rating_count,
                    }
                )
            if not found:
                # Said outright: a small model otherwise repeats the same empty
                # search until its turn runs out.
                return {
                    "businesses": [],
                    "hint": "Nothing matched. Do not repeat this search. Try once with just a "
                    "service (spa, nails, haircut) or just the city, or ask the customer.",
                }
            if widened:
                return {
                    "businesses": found,
                    "note": "Nothing matched that city or category; these match anywhere.",
                }
            return {"businesses": found}

        return await self._call_discovery("search_businesses", work)

    async def get_business_details(self, business_slug: str) -> Result:
        """A listed business's branches and the services it sells, with prices."""

        async def work(discovery: "DiscoveryService") -> Result:
            storefront = await discovery.get_storefront(business_slug)
            return {
                "business_slug": storefront.business.slug,
                "name": self._name(storefront.business),
                "branches": [
                    {"location_id": str(loc.id), "name": self._name(loc), "city": _shown(loc.city)}
                    for loc in storefront.locations
                ],
                "services": [
                    {
                        "service_id": str(svc.id),
                        "name": self._name(svc),
                        "location_id": str(svc.location_id),
                        "duration_minutes": svc.duration_minutes,
                        "price": str(svc.price),
                        "currency": svc.currency,
                    }
                    for svc in storefront.services[:30]
                    if svc.is_active
                ],
            }

        return await self._call_discovery("get_business_details", work)

    async def _listing(self, business_slug: str) -> tuple[UUID, UUID]:
        """The tenant and business behind a listing, resolved by the server from the
        slug: only a live, listed business resolves."""
        discovery = self.deps.discovery
        if discovery is None:  # pragma: no cover
            raise NotFoundError("The marketplace is not available here.")
        async with discovery() as service:
            business = (await service.get_storefront(business_slug)).business
        return UUID(str(business.tenant_id)), UUID(str(business.id))

    async def find_times_at_business(
        self, business_slug: str, service_id: str, days_ahead: int = 7
    ) -> Result:
        """Free start times for one service at a listed business. service_id is the
        service's id, or its name ("Classic Manicure")."""
        try:
            tenant_id, business_id = await self._listing(business_slug)
        except DomainError as exc:
            code, message = exc.code, exc.message
            return await self._run("find_times_at_business", lambda: _refuse(code, message))

        async def work(services: "TenantServices") -> Result:
            service = await self._service_ref(services, service_id, business_id)
            return await self._times_for_service(services, service.id, days_ahead)

        return await self._call_in("find_times_at_business", self._tenant_scope(tenant_id), work)

    async def hold_slot_at_business(
        self,
        business_slug: str,
        service_id: str,
        starts_at: datetime,
        provider_id: UUID | None = None,
    ) -> Result:
        """Holds a free time at a listed business for the customer to confirm, once they
        asked to book it.

        Pass a starts_at that find_times_at_business returned. provider_id is optional.
        """
        if self.deps.artifacts.held_slots:
            # One hold per reply. Live, a small model held a time and then kept
            # holding others instead of answering; each refusal cost a minute.
            return await self._run("hold_slot_at_business", _already_holding)
        try:
            tenant_id, business_id = await self._listing(business_slug)
        except DomainError as exc:
            code, message = exc.code, exc.message
            return await self._run("hold_slot_at_business", lambda: _refuse(code, message))
        held: list[HeldSlot] = []

        async def work(services: "TenantServices") -> Result:
            service = await self._service_ref(services, service_id, business_id)
            chosen = await self._free_provider(services, service.id, starts_at, provider_id)
            hold = await services.booking.hold_slot(
                provider_id=chosen,
                service_id=service.id,
                starts_at=starts_at,
                principal=self.deps.principal,
                customer_id=self.deps.customer_id,
            )
            details = await self._hold_details(services, hold)
            held.append(
                _held(hold, tenant_id=tenant_id, slug=business_slug, label=details["label"])
            )
            return {
                "held": True,
                "starts_at": hold.starts_at.isoformat(),
                **{k: v for k, v in details.items() if k != "label"},
                "expires_at": hold.expires_at.isoformat(),
                "next_step": _ASK_TO_CONFIRM,
            }

        result = await self._call_in("hold_slot_at_business", self._tenant_scope(tenant_id), work)
        if "error" not in result:
            self.deps.artifacts.held_slots.extend(held)
        return result

    async def get_queue_length(self, queue_id: UUID) -> Result:
        """How many people are in a walk-in queue. Nobody's name, only the count."""

        async def work(services: "TenantServices") -> Result:
            entries = await services.queue.list_queue(queue_id)
            return {"queue_id": str(queue_id), "in_line": len(entries)}

        return await self._call("get_queue_length", work)

    async def join_queue(
        self,
        queue_id: UUID,
        service_id: UUID,
        provider_id: UUID | None = None,
        party_size: int = 1,
    ) -> Result:
        """Adds the caller to a walk-in queue, and says where they stand."""
        placed: list[QueuePlace] = []

        async def work(services: "TenantServices") -> Result:
            customer_id = self.deps.customer_id
            if customer_id is None:  # pragma: no cover - the router always resolves one
                raise NotFoundError("There is no customer to add to the queue.")
            position = await services.queue.join(
                queue_id=queue_id,
                customer_reference_id=customer_id,
                self_service=self.deps.self_service,
                service_id=service_id,
                provider_id=provider_id,
                party_size=max(1, min(party_size, 20)),
            )
            placed.append(
                QueuePlace(
                    entry_id=position.entry.id,
                    queue_id=queue_id,
                    place_in_line=position.place_in_line,
                    estimated_wait_minutes=position.estimated_wait_minutes,
                )
            )
            return {
                "entry_id": str(position.entry.id),
                "place_in_line": position.place_in_line,
                "estimated_wait_minutes": position.estimated_wait_minutes,
            }

        result = await self._call("join_queue", work)
        if "error" not in result:
            # Recorded only now that the unit of work has committed.
            self.deps.artifacts.queue_places.extend(placed)
        return result

    async def get_queue_position(self, entry_id: UUID) -> Result:
        """Where the caller's own queue entry stands, and the estimated wait."""

        async def work(services: "TenantServices") -> Result:
            await services.queue.assert_entry_visible_to(entry_id, self.deps.principal)
            position = await services.queue.position_of(entry_id)
            return {
                "entry_id": str(entry_id),
                "status": str(position.entry.status),
                "place_in_line": position.place_in_line,
                "estimated_wait_minutes": position.estimated_wait_minutes,
            }

        return await self._call("get_queue_position", work)

    # --- customer service -------------------------------------------------------

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

    # --- accountant ---------------------------------------------------------------

    @staticmethod
    def _invoice(invoice: Any) -> Result:
        return {
            "invoice_id": str(invoice.id),
            "period_start": invoice.period.period_start.isoformat(),
            "period_end": invoice.period.period_end.isoformat(),
            "status": str(invoice.status),
            "subscription_amount": str(invoice.subscription_amount),
            "commission_amount": str(invoice.commission_amount),
            "processing_amount": str(invoice.processing_amount),
            "vat_amount": str(invoice.vat_amount),
            "total_amount": str(invoice.total_amount),
            "currency": invoice.currency,
            "due_at": _iso(invoice.due_at),
        }

    async def get_subscription(self) -> Result:
        """The business's plan, what it costs, and its commission rate."""

        async def work(services: "TenantServices") -> Result:
            subscription = await services.billing.subscription_or_default(self._business())
            amount = subscription.subscription_amount()
            return {
                "tier": str(subscription.tier),
                "status": str(subscription.status),
                "monthly_amount": str(amount.amount),
                "currency": amount.currency,
                "seats": subscription.seats,
                "locations": subscription.locations,
                "new_client_commission_pct": str(subscription.plan.new_client_commission_pct),
                "processing_fee_pct": str(subscription.plan.processing_fee_pct),
                "period_end": subscription.current_period_end.isoformat(),
            }

        return await self._call("get_subscription", work)

    async def list_recent_invoices(self, limit: int = 6) -> Result:
        """NOVA's most recent invoices to this business."""

        async def work(services: "TenantServices") -> Result:
            invoices = await services.billing.list_invoices(
                self._business(), limit=max(1, min(limit, 12))
            )
            return {"invoices": [self._invoice(i) for i in invoices]}

        return await self._call("list_recent_invoices", work)

    async def get_invoice(self, invoice_id: UUID) -> Result:
        """One NOVA invoice to this business."""

        async def work(services: "TenantServices") -> Result:
            invoice = await services.billing.get_invoice(invoice_id)
            if invoice.business_id != self._business():
                raise NotFoundError("There is no such invoice for this business.")
            return self._invoice(invoice)

        return await self._call("get_invoice", work)

    async def explain_commission_line(self, line_id: UUID) -> Result:
        """Why one commission line cost what it cost, in BillingService's own words."""

        async def work(services: "TenantServices") -> Result:
            return await services.billing.explain_commission_line(line_id)

        return await self._call("explain_commission_line", work)

    async def get_plan_comparison(self) -> Result:
        """The published price list, docs/11 section 2."""

        async def work(services: "TenantServices") -> Result:
            return {"plans": services.billing.plan_comparison()}

        return await self._call("get_plan_comparison", work)

    async def get_financial_summary(
        self, date_from: date | None = None, date_to: date | None = None
    ) -> Result:
        """Earned, collected, refunded, paid out and invoiced for a period (default: 30 days)."""

        async def work(services: "TenantServices") -> Result:
            report = await services.analytics.financial_summary(
                self._business(), date_from=date_from, date_to=date_to
            )
            self.deps.artifacts.metrics_used |= {"revenue", "collected", "refunded"}
            return {
                "date_from": report.window.date_from.isoformat(),
                "date_to": report.window.date_to.isoformat(),
                **{key: _text(value) for key, value in asdict(report.summary).items()},
            }

        return await self._call("get_financial_summary", work)

    # --- analyst and business manager -----------------------------------------------

    async def get_overview(
        self, date_from: date | None = None, date_to: date | None = None
    ) -> Result:
        """Every KPI for a period (default: the last 30 days). Suppressed means too little data."""

        async def work(services: "TenantServices") -> Result:
            overview = await services.analytics.overview(
                self._business(), date_from=date_from, date_to=date_to
            )
            self.deps.artifacts.metrics_used |= {str(kpi.metric) for kpi in overview.kpis}
            return {
                "date_from": overview.window.date_from.isoformat(),
                "date_to": overview.window.date_to.isoformat(),
                "days": overview.window.days,
                "currency": overview.currency,
                "kpis": {
                    str(kpi.metric): {
                        "value": _text(kpi.value),
                        "unit": str(kpi.unit),
                        "sample_size": kpi.sample_size,
                        "suppressed": kpi.suppressed,
                    }
                    for kpi in overview.kpis
                },
            }

        return await self._call("get_overview", work)

    async def get_breakdown(
        self, dimension: Dimension, date_from: date | None = None, date_to: date | None = None
    ) -> Result:
        """Bookings, completions and revenue per service, provider, source or branch."""

        async def work(services: "TenantServices") -> Result:
            report = await services.analytics.breakdown(
                self._business(), dimension, date_from=date_from, date_to=date_to
            )
            self.deps.artifacts.metrics_used |= {"bookings", "completed", "revenue"}
            return {
                "dimension": str(dimension),
                "date_from": report.window.date_from.isoformat(),
                "date_to": report.window.date_to.isoformat(),
                "currency": report.currency,
                "rows": [
                    {
                        "key": row.key,
                        "label": row.label_ar if self.deps.locale == "ar" else row.label_en,
                        "bookings": row.bookings,
                        "completed": row.completed,
                        "revenue": str(row.revenue),
                        "share_of_revenue": _text(row.share_of_revenue),
                    }
                    for row in report.rows
                ],
            }

        return await self._call("get_breakdown", work)

    async def get_forecast(
        self, metric: ForecastMetric = ForecastMetric.BOOKINGS, horizon_weeks: int = 4
    ) -> Result:
        """A straight-line weekly trend with a 95% band. A trend, not a prediction."""

        async def work(services: "TenantServices") -> Result:
            report = await services.analytics.forecast(
                self._business(), metric, horizon_weeks=horizon_weeks
            )
            self.deps.artifacts.metrics_used.add(str(metric))
            forecast = report.forecast
            return {
                "metric": str(metric),
                "method": "linear_trend",
                "currency": report.currency,
                "history_weeks": forecast.history_weeks,
                "slope_per_week": str(forecast.slope_per_week),
                "points": [
                    {
                        "week_start": point.week_start.isoformat(),
                        "value": str(point.value),
                        "lower": _text(point.lower),
                        "upper": _text(point.upper),
                        "is_forecast": point.is_forecast,
                    }
                    for point in forecast.points
                ],
            }

        return await self._call("get_forecast", work)

    async def render_chart(
        self,
        chart_id: ChartId,
        date_from: date | None = None,
        date_to: date | None = None,
        granularity: Granularity | None = None,
    ) -> Result:
        """Draws a chart for the owner. Reference it by chart_id in chart_ids."""

        async def work(services: "TenantServices") -> Result:
            if chart_id not in self.spec.charts:
                allowed = ", ".join(sorted(str(c) for c in self.spec.charts))
                return {
                    "error": "chart_not_allowed",
                    "message": f"This agent cannot draw '{chart_id}'. It can draw: {allowed}.",
                }
            report = await services.analytics.chart(
                self._business(),
                chart_id,
                date_from=date_from,
                date_to=date_to,
                granularity=granularity,
                locale=self.deps.locale,
            )
            self.deps.artifacts.charts[str(chart_id)] = report
            return {
                "chart_id": str(chart_id),
                "title": report.spec.title,
                "date_from": report.window.date_from.isoformat(),
                "date_to": report.window.date_to.isoformat(),
                "data_points": report.spec.data_points,
            }

        return await self._call("render_chart", work)

    async def list_charts(self) -> Result:
        """The charts this agent can draw, and the question each answers."""

        async def work() -> Result:
            locale = self.deps.locale
            return {
                "charts": [
                    {
                        "chart_id": str(chart_id),
                        "title": CHARTS[chart_id].title(locale),
                        "question": CHARTS[chart_id].question(locale),
                    }
                    for chart_id in sorted(self.spec.charts)
                ]
            }

        return await self._call_without_services("list_charts", work)

    async def propose_action(
        self,
        kind: ProposedActionKind,
        title: str,
        rationale: str,
        metric: str,
        target_id: UUID | None = None,
    ) -> Result:
        """Records one recommendation for the owner. Nothing is changed; a person decides."""

        async def work(services: "TenantServices") -> Result:
            artifacts = self.deps.artifacts
            try:
                parsed, rule = check_proposal(
                    str(kind),
                    metric=metric,
                    metrics_used=artifacts.metrics_used,
                    already_proposed=len(artifacts.proposed_actions),
                )
            except GuardrailError as exc:
                return {"error": exc.code, "message": exc.message}

            ungrounded = find_ungrounded_numbers(f"{title} {rationale}", artifacts.grounded_values)
            if ungrounded:
                return {
                    "error": "ungrounded_numbers",
                    "message": (
                        f"These figures were not returned by any tool: {', '.join(ungrounded)}. "
                        "Quote figures exactly as the tools returned them."
                    ),
                }

            target_id_checked = await self._check_target(services, rule.target, target_id)
            action_id = f"pa_{len(artifacts.proposed_actions) + 1}"
            artifacts.proposed_actions[action_id] = ProposedAction(
                id=action_id,
                kind=parsed,
                title=title[:200],
                rationale=rationale[:1000],
                metric=metric,
                target=rule.target,
                target_id=target_id_checked,
                apply_via=rule.apply_via,
            )
            return {
                "proposed_action_id": action_id,
                "kind": str(parsed),
                "apply_via": rule.apply_via,
            }

        return await self._call("propose_action", work)

    async def _check_target(
        self, services: "TenantServices", target: ProposalTarget, target_id: UUID | None
    ) -> UUID | None:
        """A named target must belong to this business, not merely to this tenant."""
        business_id = self._business()
        if target is ProposalTarget.BUSINESS:
            return business_id
        if target_id is None:
            return None

        catalog = services.catalog
        if target is ProposalTarget.LOCATION:
            location_id = target_id
        elif target is ProposalTarget.PROVIDER:
            location_id = (await catalog.get_provider(target_id)).location_id
        else:
            location_id = (await catalog.get_service(target_id)).location_id

        if (await catalog.get_location(location_id)).business_id != business_id:
            raise NotFoundError(f"There is no such {target} in this business.")
        return target_id


__all__ = [
    "AgentToolkit",
    "BookedTicket",
    "HeldSlot",
    "PendingCancellation",
    "QueuePlace",
    "decode_offers",
    "encode_offers",
]


def _fold(text: str | None) -> str:
    """Case- and accent-insensitive text, for matching a service by name."""
    decomposed = unicodedata.normalize("NFKD", (text or "").casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip()


class _TimeNotFree(ConflictError):
    code = "time_not_free"


def _local(moment: datetime, timezone: str) -> str:
    """A time as the branch's customers read it: `Thu 24 Sep 2026, 20:00 (Asia/Riyadh)`.

    The ISO time is UTC. A small model restating it gets the day and hour
    wrong, so each time is also given ready to repeat."""
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("Asia/Riyadh")
    return f"{moment.astimezone(zone):%a %d %b %Y, %H:%M} ({zone.key})"


#: Told to the model with every hold, before it can try to book too early.
_ASK_TO_CONFIRM = (
    "Now reply to the customer naming the business, the service and the held local_time, "
    "and ask: shall I book it? "
    'They confirm by pressing "Yes, book it" under the time; it is booked only then.'
)

#: What a small model writes into an optional argument it has no value for.
_PLACEHOLDERS = frozenset({"unknown", "any", "none", "null", "n/a", "na", "all", "anywhere", "-"})


def _given(value: str | None) -> str | None:
    """A search filter the customer actually gave, or None."""
    text = (value or "").strip()[:120]
    return None if not text or text.lower() in _PLACEHOLDERS else text


async def _already_holding() -> Result:
    return {
        "error": "already_holding",
        "message": "A time is already held in this reply. Stop calling tools. " + _ASK_TO_CONFIRM,
    }


async def _refuse(code: str, message: str) -> Result:
    """A refusal shaped like a domain error's, for a tool that stops before any work."""
    return {"error": code, "message": message}
