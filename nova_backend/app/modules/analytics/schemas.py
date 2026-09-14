"""analytics · CONTRACT layer — API boundary DTOs (docs/13 sections 7.1 and 9).

Layer rule: pydantic only. Money and ratios are `Decimal`, so they serialise as
exact strings; only `figure` carries floats, and it is presentation.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.schemas import ApiSchema
from app.modules.analytics.domain import (
    ChartId,
    ChartKind,
    Dimension,
    ForecastMetric,
    Granularity,
    MetricName,
    MetricUnit,
)


class ReportWindowOut(ApiSchema):
    date_from: date
    date_to: date
    timezone: str
    days: int


class KpiOut(ApiSchema):
    metric: MetricName
    #: Null exactly when `suppressed`: the sample was too small to report.
    value: Decimal | None
    unit: MetricUnit
    sample_size: int
    suppressed: bool


class OverviewOut(ApiSchema):
    business_id: UUID
    window: ReportWindowOut
    currency: str
    #: Rows left out because they were in another currency (ADR-0009).
    excluded_rows: int
    kpis: list[KpiOut]


class BreakdownRowOut(ApiSchema):
    dimension: Dimension
    key: str
    label: str
    label_en: str
    label_ar: str
    bookings: int
    completed: int
    revenue: Decimal
    share_of_revenue: Decimal | None


class ChartCatalogEntryOut(ApiSchema):
    chart_id: ChartId
    kind: ChartKind
    title_en: str
    title_ar: str
    question_en: str
    question_ar: str
    required_feature: str | None


class ChartOut(ApiSchema):
    """docs/13 section 7.1. `figure` is Plotly JSON for plotly.js to draw."""

    chart_id: ChartId
    kind: ChartKind
    title: str
    description: str
    locale: str
    business_id: UUID
    date_from: date
    date_to: date
    granularity: Granularity | None
    currency: str
    data_points: int
    generated_at: datetime
    figure: dict[str, Any]


class ForecastPointOut(ApiSchema):
    week_start: date
    value: Decimal
    lower: Decimal | None
    upper: Decimal | None
    is_forecast: bool


class ForecastOut(ApiSchema):
    business_id: UUID
    metric: ForecastMetric
    currency: str
    #: Named in the contract so no client mistakes a trend line for a model.
    method: str = "linear_trend"
    history_weeks: int
    slope_per_week: Decimal
    points: list[ForecastPointOut]


class FinancialSummaryOut(ApiSchema):
    business_id: UUID
    window: ReportWindowOut
    currency: str
    revenue: Decimal
    collected: Decimal
    refunded: Decimal
    commission_accrued: Decimal
    commission_reversed: Decimal
    payouts_collected: Decimal
    payouts_processing_fees: Decimal
    payouts_commission_netted: Decimal
    payouts_net: Decimal
    invoiced_subscription: Decimal
    invoiced_commission: Decimal
    invoiced_processing: Decimal
    invoiced_vat: Decimal
    invoiced_total: Decimal
    outstanding_invoices: int
    outstanding_total: Decimal
