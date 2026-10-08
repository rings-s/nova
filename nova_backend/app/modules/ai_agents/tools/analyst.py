"""ai_agents · tools — the analyst and business manager: overviews, breakdowns,
forecasts, charts, and proposed actions, which are never applied.
"""

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from app.core.exceptions import NotFoundError
from app.modules.ai_agents.guardrails import (
    GuardrailError,
    ProposalTarget,
    ProposedAction,
    ProposedActionKind,
    check_proposal,
    find_ungrounded_numbers,
)
from app.modules.analytics.domain import CHARTS, ChartId, Dimension, ForecastMetric, Granularity

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.ai_agents.service import TenantServices

from app.modules.ai_agents.tools.base import (
    Result,
    ToolkitBase,
    _text,
)


class AnalystTools(ToolkitBase):
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
