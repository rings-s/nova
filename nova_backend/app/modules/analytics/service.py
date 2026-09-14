"""analytics · APPLICATION layer — load facts, compute, draw.

Layer rule: other modules' *services* only, and this module's domain, metrics
and charts. No repository, no models, no fastapi. This file never imports
pandas or plotly either: it hands facts to `metrics.py` and frames to
`charts.py`, and passes their results along without looking inside.

Read-only, so nothing here flushes. Facts are memoised on the instance for the
life of one request, so an AI agent that calls three tools in a turn hits the
database once per fact set.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.values import TimeRange
from app.modules.analytics import charts, metrics
from app.modules.analytics.domain import (
    CHARTS,
    CROSS_LOCATION_FEATURE,
    MAX_FACT_ROWS,
    MAX_FORECAST_HISTORY_WEEKS,
    MAX_FORECAST_HORIZON_WEEKS,
    SOURCE_LABELS,
    BreakdownRow,
    ChartDefinition,
    ChartId,
    ChartSpec,
    Dimension,
    FinancialSummary,
    Forecast,
    ForecastMetric,
    Granularity,
    Kpi,
    ReportWindow,
    build_window,
    resolve_granularity,
)
from app.modules.analytics.exceptions import ReportTooLargeError
from app.modules.billing.service import BillingService
from app.modules.booking.service import BookingService
from app.modules.catalog.service import CatalogService
from app.modules.payment.service import PaymentService
from app.modules.queue.service import QueueService

#: How far before a window payments are read, so a booking completed in August
#: but prepaid in July still counts as prepaid. Matches the booking horizon.
PREPAYMENT_LOOKBACK_DAYS = 90

#: `businesses_for` issues one `IN (...)`; asyncpg caps parameters at 32,767.
_ID_CHUNK = 5_000


@dataclass(frozen=True)
class BusinessContext:
    business_id: UUID
    timezone: str
    location_ids: list[UUID]
    location_timezones: dict[str, str]
    provider_ids: list[UUID]
    labels: dict[Dimension, dict[str, tuple[str, str]]] = field(default_factory=dict)


@dataclass(frozen=True)
class Overview:
    business_id: UUID
    window: ReportWindow
    currency: str
    excluded_rows: int
    kpis: list[Kpi]


@dataclass(frozen=True)
class BreakdownReport:
    business_id: UUID
    window: ReportWindow
    dimension: Dimension
    currency: str
    rows: list[BreakdownRow]


@dataclass(frozen=True)
class ChartReport:
    spec: ChartSpec
    business_id: UUID
    window: ReportWindow
    granularity: Granularity | None
    currency: str
    generated_at: datetime


@dataclass(frozen=True)
class ForecastReport:
    business_id: UUID
    window: ReportWindow
    currency: str
    forecast: Forecast


@dataclass(frozen=True)
class FinancialReport:
    business_id: UUID
    window: ReportWindow
    summary: FinancialSummary


class AnalyticsService:
    def __init__(
        self,
        *,
        tenant_id: UUID,
        catalog: CatalogService,
        bookings: BookingService,
        payments: PaymentService,
        queues: QueueService,
        billing: BillingService,
        default_currency: str = "SAR",
        default_timezone: str = "Asia/Riyadh",
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.catalog = catalog
        self.bookings = bookings
        self.payments = payments
        self.queues = queues
        self.billing = billing
        self.default_currency = default_currency
        self.default_timezone = default_timezone
        self._now = now or (lambda: datetime.now(UTC))
        self._memo: dict[tuple[Any, ...], Any] = {}

    # --- public reads ---------------------------------------------------------

    def catalogue(self) -> list[ChartDefinition]:
        return list(CHARTS.values())

    async def overview(
        self, business_id: UUID, *, date_from: date | None = None, date_to: date | None = None
    ) -> Overview:
        business = await self._business(business_id)
        window = self._window(business, date_from, date_to)
        bookings, currency, excluded = await self._bookings(business, window)
        payments = await self._payments(business, window, currency)
        visits = await self._visits(business)
        capacity = await self._capacity(business, window)
        queue = await self._queue(business, window)
        kpis = [
            *metrics.booking_kpis(bookings),
            *metrics.payment_kpis(payments, bookings, window),
            *metrics.customer_kpis(bookings, visits, window),
            metrics.utilization_kpi(metrics.utilization_frame(bookings, capacity, window)),
            *metrics.queue_kpis(queue),
        ]
        return Overview(business_id, window, currency, excluded, kpis)

    async def breakdown(
        self,
        business_id: UUID,
        dimension: Dimension,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> BreakdownReport:
        if dimension is Dimension.LOCATION:
            await self.billing.require_feature(business_id, CROSS_LOCATION_FEATURE)
        business = await self._business(business_id)
        window = self._window(business, date_from, date_to)
        bookings, currency, _ = await self._bookings(business, window)
        rows = metrics.breakdown(bookings, dimension, self._labels(business, dimension))
        return BreakdownReport(business_id, window, dimension, currency, rows)

    async def forecast(
        self, business_id: UUID, metric: ForecastMetric, *, horizon_weeks: int = 4
    ) -> ForecastReport:
        business = await self._business(business_id)
        today = self._today(business)
        window = build_window(
            date_from=today - timedelta(weeks=MAX_FORECAST_HISTORY_WEEKS + 1),
            date_to=today,
            timezone=business.timezone,
            today=today,
        )
        bookings, currency, _ = await self._bookings(business, window)
        history = metrics.weekly_history(
            bookings, metric=metric, timezone=business.timezone, as_of=self._now()
        )
        horizon = max(1, min(horizon_weeks, MAX_FORECAST_HORIZON_WEEKS))
        forecast = metrics.linear_forecast(history, metric=metric, horizon_weeks=horizon)
        return ForecastReport(business_id, window, currency, forecast)

    async def financial_summary(
        self, business_id: UUID, *, date_from: date | None = None, date_to: date | None = None
    ) -> FinancialReport:
        business = await self._business(business_id)
        window = self._window(business, date_from, date_to)
        bookings, currency, _ = await self._bookings(business, window)
        payments = await self._payments(business, window, currency)
        lines, invoices, payouts = await self._ledger(business, window)
        summary = metrics.financial_summary(
            bookings=bookings,
            payments=payments,
            lines=lines,
            invoices=invoices,
            payouts=payouts,
            window=window,
            currency=currency,
        )
        return FinancialReport(business_id, window, summary)

    async def chart(
        self,
        business_id: UUID,
        chart_id: ChartId,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        granularity: Granularity | None = None,
        locale: str = "en",
    ) -> ChartReport:
        definition = CHARTS[chart_id]
        if definition.required_feature is not None:
            await self.billing.require_feature(business_id, definition.required_feature)

        if chart_id is ChartId.BOOKINGS_FORECAST:
            report = await self.forecast(business_id, ForecastMetric.BOOKINGS)
            return ChartReport(
                spec=charts.bookings_forecast(report.forecast, locale=locale),
                business_id=business_id,
                window=report.window,
                granularity=Granularity.WEEK,
                currency=report.currency,
                generated_at=self._now(),
            )

        business = await self._business(business_id)
        window = self._window(business, date_from, date_to)
        step = resolve_granularity(window, granularity)
        spec, currency = await self._build(chart_id, business, window, step, locale)
        return ChartReport(spec, business_id, window, step, currency, self._now())

    # --- chart dispatch ---------------------------------------------------------

    async def _build(
        self,
        chart_id: ChartId,
        business: BusinessContext,
        window: ReportWindow,
        step: Granularity,
        locale: str,
    ) -> tuple[ChartSpec, str]:
        bookings, currency, _ = await self._bookings(business, window)

        if chart_id is ChartId.BOOKINGS_TREND:
            table = metrics.outcome_series(bookings, window, step)
            return charts.bookings_trend(table, locale=locale), currency
        if chart_id is ChartId.BOOKING_OUTCOMES:
            table = metrics.outcome_series(bookings, window, step)
            return charts.booking_outcomes(table, locale=locale), currency
        if chart_id is ChartId.REVENUE_TREND:
            series = metrics.revenue_series(bookings, window, step)
            return charts.revenue_trend(series, locale=locale, currency=currency), currency
        if chart_id in (
            ChartId.REVENUE_BY_SERVICE,
            ChartId.REVENUE_BY_PROVIDER,
            ChartId.REVENUE_BY_LOCATION,
        ):
            dimension = {
                ChartId.REVENUE_BY_SERVICE: Dimension.SERVICE,
                ChartId.REVENUE_BY_PROVIDER: Dimension.PROVIDER,
                ChartId.REVENUE_BY_LOCATION: Dimension.LOCATION,
            }[chart_id]
            rows = metrics.breakdown(bookings, dimension, self._labels(business, dimension))
            builder = {
                Dimension.SERVICE: charts.revenue_by_service,
                Dimension.PROVIDER: charts.revenue_by_provider,
                Dimension.LOCATION: charts.revenue_by_location,
            }[dimension]
            return builder(rows, locale=locale, currency=currency), currency
        if chart_id is ChartId.SOURCE_MIX:
            rows = metrics.breakdown(bookings, Dimension.SOURCE, SOURCE_LABELS)
            return charts.source_mix(rows, locale=locale), currency
        if chart_id is ChartId.NEW_VS_RETURNING:
            visits = await self._visits(business)
            table = metrics.new_vs_returning_series(bookings, visits, window, step)
            return charts.new_vs_returning(table, locale=locale), currency
        if chart_id is ChartId.RETENTION_COHORTS:
            visits = await self._visits(business)
            matrix = metrics.retention_matrix(bookings, visits, window)
            return charts.retention_cohorts(matrix, locale=locale), currency
        if chart_id is ChartId.PEAK_HOURS:
            matrix = metrics.peak_hours_matrix(
                bookings, business.location_timezones, default_timezone=business.timezone
            )
            return charts.peak_hours(matrix, locale=locale), currency
        if chart_id is ChartId.PROVIDER_UTILIZATION:
            capacity = await self._capacity(business, window)
            frame = metrics.utilization_frame(bookings, capacity, window)
            labels = business.labels[Dimension.PROVIDER]
            return charts.provider_utilization(frame, labels, locale=locale), currency
        if chart_id is ChartId.QUEUE_WAIT_TIMES:
            queue = await self._queue(business, window)
            series = metrics.queue_wait_series(queue, window, step)
            return charts.queue_wait_times(series, locale=locale), currency

        lines, invoices, payouts = await self._ledger(business, window)
        if chart_id is ChartId.PAYOUTS_BREAKDOWN:
            frame = metrics.payouts_frame(payouts, currency=currency)
            return charts.payouts_breakdown(frame, locale=locale, currency=currency), currency
        if chart_id is ChartId.NOVA_CHARGES:
            frame = metrics.invoices_frame(invoices, currency=currency)
            return charts.nova_charges(frame, locale=locale, currency=currency), currency
        frame = metrics.commission_by_class(lines, currency=currency)
        return charts.commission_by_class(frame, locale=locale, currency=currency), currency

    # --- context and windows ------------------------------------------------------

    async def _business(self, business_id: UUID) -> BusinessContext:
        """The business, its branches and its labels. 404 outside this tenant."""
        key = ("business", business_id)
        if key in self._memo:
            return self._memo[key]

        await self.catalog.get_business(business_id)
        locations = await self.catalog.list_locations(business_id)
        labels: dict[Dimension, dict[str, tuple[str, str]]] = {
            Dimension.SERVICE: {},
            Dimension.PROVIDER: {},
            Dimension.LOCATION: {},
        }
        provider_ids: list[UUID] = []
        for location in locations:
            labels[Dimension.LOCATION][str(location.id)] = (location.name_en, location.name_ar)
            for service in await self.catalog.list_services(location.id):
                labels[Dimension.SERVICE][str(service.id)] = (service.name_en, service.name_ar)
            for provider in await self.catalog.list_providers(location.id):
                labels[Dimension.PROVIDER][str(provider.id)] = (provider.name_en, provider.name_ar)
                if provider.is_active:
                    provider_ids.append(provider.id)

        context = BusinessContext(
            business_id=business_id,
            # Series bucket in the primary branch's timezone (docs/13 s6.3).
            timezone=locations[0].timezone if locations else self.default_timezone,
            location_ids=[location.id for location in locations],
            location_timezones={str(location.id): location.timezone for location in locations},
            provider_ids=provider_ids,
            labels=labels,
        )
        self._memo[key] = context
        return context

    def _labels(
        self, business: BusinessContext, dimension: Dimension
    ) -> dict[str, tuple[str, str]]:
        return SOURCE_LABELS if dimension is Dimension.SOURCE else business.labels[dimension]

    def _today(self, business: BusinessContext) -> date:
        return self._now().astimezone(ZoneInfo(business.timezone)).date()

    def _window(
        self, business: BusinessContext, date_from: date | None, date_to: date | None
    ) -> ReportWindow:
        return build_window(
            date_from=date_from,
            date_to=date_to,
            timezone=business.timezone,
            today=self._today(business),
        )

    # --- facts ------------------------------------------------------------------

    @staticmethod
    async def _capped[T](what: str, load: Callable[[int], Awaitable[list[T]]]) -> list[T]:
        """Loads one row past the cap, so "exactly at the cap" and "over it" differ."""
        rows = await load(MAX_FACT_ROWS + 1)
        if len(rows) > MAX_FACT_ROWS:
            raise ReportTooLargeError(what, MAX_FACT_ROWS)
        return rows

    @staticmethod
    def _range(window: ReportWindow) -> TimeRange:
        return TimeRange(starts_at=window.starts_at, ends_at=window.ends_at)

    async def _bookings(
        self, business: BusinessContext, window: ReportWindow
    ) -> tuple[Any, str, int]:
        key = ("bookings", business.business_id, window)
        if key not in self._memo:
            facts = await self._capped(
                "bookings",
                lambda limit: self.bookings.list_booking_facts(
                    business_id=business.business_id, window=self._range(window), limit=limit
                ),
            )
            currency = metrics.primary_currency(
                (fact.currency for fact in facts), default=self.default_currency
            )
            frame, excluded = metrics.booking_frame(facts, currency=currency)
            self._memo[key] = (frame, currency, excluded)
        return self._memo[key]

    async def _payments(
        self, business: BusinessContext, window: ReportWindow, currency: str
    ) -> Any:
        key = ("payments", business.business_id, window, currency)
        if key not in self._memo:
            reach_back = TimeRange(
                starts_at=window.starts_at - timedelta(days=PREPAYMENT_LOOKBACK_DAYS),
                ends_at=window.ends_at,
            )
            facts = await self._capped(
                "payments",
                lambda limit: self.payments.list_payment_facts(window=reach_back, limit=limit),
            )
            # Payments know their booking, not their business; booking answers
            # that, service to service, in chunks the driver accepts.
            owners: dict[UUID, UUID] = {}
            booking_ids = list({fact.booking_id for fact in facts})
            for chunk in _chunks(booking_ids, _ID_CHUNK):
                owners.update(await self.bookings.businesses_for(chunk))
            mine = [fact for fact in facts if owners.get(fact.booking_id) == business.business_id]
            frame, _ = metrics.payment_frame(mine, currency=currency)
            self._memo[key] = frame
        return self._memo[key]

    async def _visits(self, business: BusinessContext) -> Any:
        key = ("visits", business.business_id)
        if key not in self._memo:
            facts = await self._capped(
                "customers",
                lambda limit: self.bookings.list_customer_visit_facts(
                    business_id=business.business_id, as_of=self._now(), limit=limit
                ),
            )
            self._memo[key] = metrics.visit_frame(facts)
        return self._memo[key]

    async def _capacity(self, business: BusinessContext, window: ReportWindow) -> Any:
        key = ("capacity", business.business_id, window)
        if key not in self._memo:
            self._memo[key] = await self.bookings.list_capacity_facts(
                provider_ids=business.provider_ids,
                date_from=window.date_from,
                date_to=window.date_to,
            )
        return self._memo[key]

    async def _queue(self, business: BusinessContext, window: ReportWindow) -> Any:
        key = ("queue", business.business_id, window)
        if key not in self._memo:
            facts = await self._capped(
                "queue entries",
                lambda limit: self.queues.list_queue_facts(
                    location_ids=business.location_ids, window=self._range(window), limit=limit
                ),
            )
            self._memo[key] = metrics.queue_frame(facts)
        return self._memo[key]

    async def _ledger(
        self, business: BusinessContext, window: ReportWindow
    ) -> tuple[Any, Any, Any]:
        key = ("ledger", business.business_id, window)
        if key not in self._memo:
            business_id = business.business_id
            lines = await self._capped(
                "commission lines",
                lambda limit: self.billing.list_commission_lines_between(
                    business_id, starts_at=window.starts_at, ends_at=window.ends_at, limit=limit
                ),
            )
            invoices = await self._capped(
                "invoices",
                lambda limit: self.billing.list_invoices_between(
                    business_id, date_from=window.date_from, date_to=window.date_to, limit=limit
                ),
            )
            payouts = await self._capped(
                "payouts",
                lambda limit: self.billing.list_payouts_between(
                    business_id, date_from=window.date_from, date_to=window.date_to, limit=limit
                ),
            )
            self._memo[key] = (lines, invoices, payouts)
        return self._memo[key]


def _chunks[T](items: Sequence[T], size: int) -> list[Sequence[T]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


__all__ = [
    "AnalyticsService",
    "BreakdownReport",
    "ChartReport",
    "FinancialReport",
    "ForecastReport",
    "Overview",
]
