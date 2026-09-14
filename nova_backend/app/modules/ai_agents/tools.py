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
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.core.exceptions import DomainError, NotFoundError
from app.modules.ai_agents.agents import WRITE_TOOLS, AgentSpec
from app.modules.ai_agents.guardrails import (
    GuardrailError,
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
    from app.modules.ai_agents.service import AgentDeps, TenantServices

logger = logging.getLogger(__name__)

Result = dict[str, Any]
#: A tool's body, given the services of the unit of work it runs in.
Work = Callable[["TenantServices"], Awaitable[Result]]


@dataclass(frozen=True)
class HeldSlot:
    """A slot a tool held this turn. The client books it with `hold_token`."""

    hold_token: str
    provider_id: UUID
    service_id: UUID
    starts_at: datetime
    ends_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class QueuePlace:
    """A place a tool took in a walk-in queue this turn."""

    entry_id: UUID
    queue_id: UUID
    place_in_line: int
    estimated_wait_minutes: int | None


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text(value: Any) -> Any:
    return str(value) if isinstance(value, Decimal) else value


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

        async def in_unit_of_work() -> Result:
            async with self.deps.services() as services:
                return await work(services)

        return await self._run(tool_name, in_unit_of_work)

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
        return record.name_ar if self.deps.locale == "ar" else record.name_en

    # --- receptionist -----------------------------------------------------------

    async def search_services(self, location_id: UUID) -> Result:
        """The services a branch sells: name, duration and price."""

        async def work(services: "TenantServices") -> Result:
            offered = await services.catalog.list_services(location_id)
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
                ]
            }

        return await self._call("search_services", work)

    async def get_provider_info(self, provider_id: UUID) -> Result:
        """A provider's name and title."""

        async def work(services: "TenantServices") -> Result:
            provider = await services.catalog.get_provider(provider_id)
            title = provider.title_ar if self.deps.locale == "ar" else provider.title_en
            return {"provider_id": str(provider.id), "name": self._name(provider), "title": title}

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

    async def hold_slot(self, provider_id: UUID, service_id: UUID, starts_at: datetime) -> Result:
        """Holds a time for a few minutes while the customer pays. It cannot confirm."""
        held: list[HeldSlot] = []

        async def work(services: "TenantServices") -> Result:
            hold = await services.booking.hold_slot(
                provider_id=provider_id,
                service_id=service_id,
                starts_at=starts_at,
                customer_id=self.deps.customer_id,
            )
            held.append(
                HeldSlot(
                    hold_token=hold.hold_token,
                    provider_id=hold.provider_id,
                    service_id=hold.service_id,
                    starts_at=hold.starts_at,
                    ends_at=hold.ends_at,
                    expires_at=hold.expires_at,
                )
            )
            # No token here. It is a bearer credential for the slot, the
            # response hands it to the client, and the model has no use for it:
            # the prompt, the logs and conversation memory are no place for it.
            return {
                "held": True,
                "starts_at": hold.starts_at.isoformat(),
                "expires_at": hold.expires_at.isoformat(),
            }

        result = await self._call("hold_slot", work)
        if "error" not in result:
            # Recorded only now that the unit of work has committed.
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

    @staticmethod
    def _booking(booking: Any) -> Result:
        # No notes and nothing about the customer: this goes into a prompt.
        return {
            "booking_id": str(booking.id),
            "status": str(booking.status),
            "starts_at": booking.slot.starts_at.isoformat(),
            "service_id": str(booking.service_id),
            "provider_id": str(booking.provider_id),
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
            return {"bookings": [self._booking(b) for b in bookings]}

        return await self._call("list_my_bookings", work)

    async def get_booking_status(self, booking_id: UUID) -> Result:
        """One booking, if the caller may see it. Otherwise "not found"."""

        async def work(services: "TenantServices") -> Result:
            booking = await services.booking.get_for_principal(booking_id, self.deps.principal)
            return self._booking(booking)

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

    async def cancel_booking(self, booking_id: UUID, reason: str | None = None) -> Result:
        """Cancels one of the caller's bookings, under the business's cancellation policy.

        `by_staff` is not a parameter here, so the policy cannot be waived by
        asking nicely.
        """

        async def work(services: "TenantServices") -> Result:
            await services.booking.assert_visible_to(booking_id, self.deps.principal)
            booking = await services.booking.cancel(booking_id, reason=reason)
            return {"booking_id": str(booking.id), "status": str(booking.status)}

        result = await self._call("cancel_booking", work)
        if "error" not in result:
            # Recorded only now that the unit of work has committed.
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


__all__ = ["AgentToolkit", "HeldSlot", "QueuePlace"]
