"""ai_agents · tools — what every tool shares: the unit-of-work runner `_run`,
the records a turn hands the client, and the text and time helpers.

`ToolkitBase._run` is where the four things in the package docstring happen
around every call. The agent mixins beside this file only add tools.
"""

import asyncio
import json
import logging
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core import metrics
from app.core.config import get_settings
from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.modules.ai_agents.agents import WRITE_TOOLS, AgentSpec
from app.modules.ai_agents.guardrails import (
    GuardrailError,
    GuardrailViolation,
    assert_tool_allowed,
    grounded_values_in_result,
)

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
_MIN_LEAD_MINUTES = 30


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


class ToolkitBase:
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
        metrics.count(
            "nova_ai_tool_calls_total",
            tool=tool_name,
            outcome="refused" if "error" in result else "ok",
        )
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
        zone = ZoneInfo(get_settings().default_timezone)
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
