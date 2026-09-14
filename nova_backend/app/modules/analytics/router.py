"""analytics · DELIVERY layer — HTTP (docs/13 section 9).

Layer rule: schemas, service, dependencies. No business rules here.

Gated by role throughout (`view_analytics`: owners and managers). These are a
salon's own numbers, revenue by provider among them: a customer principal,
which reaches every tenant by design, has no business reading them, and neither
does a stylist reading a colleague's takings. The financial summary also needs
`view_financials`. They are reads, so the default rate limit applies rather
than the write one; a long window is still real database work, and the service
caps it.
"""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.schemas import Page
from app.core.throttling import default_rate_limit
from app.modules.analytics.dependencies import get_analytics_service
from app.modules.analytics.domain import (
    Dimension,
    ForecastMetric,
    Granularity,
    ReportWindow,
    parse_chart_id,
)
from app.modules.analytics.schemas import (
    BreakdownRowOut,
    ChartCatalogEntryOut,
    ChartOut,
    FinancialSummaryOut,
    ForecastOut,
    ForecastPointOut,
    KpiOut,
    OverviewOut,
    ReportWindowOut,
)
from app.modules.analytics.service import AnalyticsService
from app.modules.identity.dependencies import RequirePermission
from app.modules.identity.domain import StaffPermission

Locale = Literal["en", "ar"]

router = APIRouter(
    prefix="/tenants/{tenant_id}/analytics",
    tags=["analytics"],
    dependencies=[
        Depends(RequirePermission(StaffPermission.VIEW_ANALYTICS)),
        Depends(default_rate_limit),
    ],
)


def _window_out(window: ReportWindow) -> ReportWindowOut:
    return ReportWindowOut(
        date_from=window.date_from,
        date_to=window.date_to,
        timezone=window.timezone,
        days=window.days,
    )


@router.get("/charts", response_model=Page[ChartCatalogEntryOut])
async def list_charts(
    tenant_id: UUID,
    service: AnalyticsService = Depends(get_analytics_service),
) -> Page[ChartCatalogEntryOut]:
    """The chart catalog (docs/13 section 7), with the plan feature each needs."""
    entries = [
        ChartCatalogEntryOut(
            chart_id=definition.chart_id,
            kind=definition.kind,
            title_en=definition.title_en,
            title_ar=definition.title_ar,
            question_en=definition.question_en,
            question_ar=definition.question_ar,
            required_feature=definition.required_feature,
        )
        for definition in service.catalogue()
    ]
    return Page(items=entries, total=len(entries))


@router.get("/charts/{chart_id}", response_model=ChartOut)
async def get_chart(
    tenant_id: UUID,
    chart_id: str,
    business_id: UUID = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    granularity: Granularity | None = Query(default=None),
    locale: Locale = Query(default="en"),
    service: AnalyticsService = Depends(get_analytics_service),
) -> ChartOut:
    """One chart as Plotly JSON, for plotly.js to draw."""
    report = await service.chart(
        business_id,
        parse_chart_id(chart_id),
        date_from=date_from,
        date_to=date_to,
        granularity=granularity,
        locale=locale,
    )
    spec = report.spec
    return ChartOut(
        chart_id=spec.chart_id,
        kind=spec.kind,
        title=spec.title,
        description=spec.description,
        locale=spec.locale,
        business_id=report.business_id,
        date_from=report.window.date_from,
        date_to=report.window.date_to,
        granularity=report.granularity,
        currency=report.currency,
        data_points=spec.data_points,
        generated_at=report.generated_at,
        figure=spec.figure,
    )


@router.get("/overview", response_model=OverviewOut)
async def get_overview(
    tenant_id: UUID,
    business_id: UUID = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    service: AnalyticsService = Depends(get_analytics_service),
) -> OverviewOut:
    """Every KPI in docs/13 section 6.4. A suppressed one has a null value."""
    overview = await service.overview(business_id, date_from=date_from, date_to=date_to)
    return OverviewOut(
        business_id=overview.business_id,
        window=_window_out(overview.window),
        currency=overview.currency,
        excluded_rows=overview.excluded_rows,
        kpis=[
            KpiOut(
                metric=kpi.metric,
                value=kpi.value,
                unit=kpi.unit,
                sample_size=kpi.sample_size,
                suppressed=kpi.suppressed,
            )
            for kpi in overview.kpis
        ],
    )


@router.get("/breakdown", response_model=Page[BreakdownRowOut])
async def get_breakdown(
    tenant_id: UUID,
    business_id: UUID = Query(...),
    dimension: Dimension = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    locale: Locale = Query(default="en"),
    service: AnalyticsService = Depends(get_analytics_service),
) -> Page[BreakdownRowOut]:
    """Per service, provider, source, or (on Chain) branch."""
    report = await service.breakdown(business_id, dimension, date_from=date_from, date_to=date_to)
    rows = [
        BreakdownRowOut(
            dimension=report.dimension,
            key=row.key,
            label=row.label_ar if locale == "ar" else row.label_en,
            label_en=row.label_en,
            label_ar=row.label_ar,
            bookings=row.bookings,
            completed=row.completed,
            revenue=row.revenue,
            share_of_revenue=row.share_of_revenue,
        )
        for row in report.rows
    ]
    return Page(items=rows, total=len(rows))


@router.get("/forecast", response_model=ForecastOut)
async def get_forecast(
    tenant_id: UUID,
    business_id: UUID = Query(...),
    metric: ForecastMetric = Query(default=ForecastMetric.BOOKINGS),
    horizon_weeks: int = Query(default=4, ge=1, le=8),
    service: AnalyticsService = Depends(get_analytics_service),
) -> ForecastOut:
    """A linear trend over complete weeks (docs/13 section 10), never a promise."""
    report = await service.forecast(business_id, metric, horizon_weeks=horizon_weeks)
    forecast = report.forecast
    return ForecastOut(
        business_id=report.business_id,
        metric=forecast.metric,
        currency=report.currency,
        history_weeks=forecast.history_weeks,
        slope_per_week=forecast.slope_per_week,
        points=[
            ForecastPointOut(
                week_start=point.week_start,
                value=point.value,
                lower=point.lower,
                upper=point.upper,
                is_forecast=point.is_forecast,
            )
            for point in forecast.points
        ],
    )


@router.get(
    "/financial-summary",
    response_model=FinancialSummaryOut,
    dependencies=[Depends(RequirePermission(StaffPermission.VIEW_FINANCIALS))],
)
async def get_financial_summary(
    tenant_id: UUID,
    business_id: UUID = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    service: AnalyticsService = Depends(get_analytics_service),
) -> FinancialSummaryOut:
    """The accountant's ledger for one window.

    Needs `view_financials` as well as the router's `view_analytics`: it shows
    payouts, commission and what NOVA invoiced, not a dashboard.
    """
    report = await service.financial_summary(business_id, date_from=date_from, date_to=date_to)
    summary = report.summary
    return FinancialSummaryOut(
        business_id=report.business_id,
        window=_window_out(report.window),
        currency=summary.currency,
        revenue=summary.revenue,
        collected=summary.collected,
        refunded=summary.refunded,
        commission_accrued=summary.commission_accrued,
        commission_reversed=summary.commission_reversed,
        payouts_collected=summary.payouts_collected,
        payouts_processing_fees=summary.payouts_processing_fees,
        payouts_commission_netted=summary.payouts_commission_netted,
        payouts_net=summary.payouts_net,
        invoiced_subscription=summary.invoiced_subscription,
        invoiced_commission=summary.invoiced_commission,
        invoiced_processing=summary.invoiced_processing,
        invoiced_vat=summary.invoiced_vat,
        invoiced_total=summary.invoiced_total,
        outstanding_invoices=summary.outstanding_invoices,
        outstanding_total=summary.outstanding_total,
    )
