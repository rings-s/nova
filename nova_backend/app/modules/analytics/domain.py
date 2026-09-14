"""analytics · DOMAIN layer — windows, names, thresholds and result values.

Layer rule: stdlib, pydantic and `app.core` only. No pandas here: the rules
about what a report may say (how long a window, how small a sample) are plain
Python so they read as rules. `metrics.py` is where the arithmetic lives.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from app.modules.analytics.exceptions import ReportWindowError, UnknownChartError

# --- limits (docs/13 section 6.3 and 6.4) ----------------------------------

MAX_WINDOW_DAYS = 400
DEFAULT_WINDOW_DAYS = 30
#: A fact query past this is refused, never truncated.
MAX_FACT_ROWS = 50_000
#: Rates below this many observations are suppressed rather than reported.
MIN_SAMPLE = 20
#: Retention cohorts smaller than this are hidden: a cohort of two customers is
#: a rumour about two people, not a rate.
MIN_COHORT_SIZE = 5
MIN_FORECAST_WEEKS = 8
MAX_FORECAST_HISTORY_WEEKS = 26
MAX_FORECAST_HORIZON_WEEKS = 8
#: A customer is lapsed when their last visit is this old, but not so old that
#: they are simply gone.
LAPSED_AFTER_DAYS = 60
LAPSED_UNTIL_DAYS = 365
TOP_N = 10

#: docs/11 section 2: branch-by-branch comparison is a Chain feature.
CROSS_LOCATION_FEATURE = "cross_location_reporting"


class Granularity(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class Dimension(StrEnum):
    SERVICE = "service"
    PROVIDER = "provider"
    LOCATION = "location"
    SOURCE = "source"


class ForecastMetric(StrEnum):
    BOOKINGS = "bookings"
    REVENUE = "revenue"


class MetricUnit(StrEnum):
    COUNT = "count"
    MONEY = "money"
    RATIO = "ratio"
    HOURS = "hours"
    MINUTES = "minutes"


class MetricName(StrEnum):
    """docs/13 section 6.4. The names an agent may cite in `metrics_used`."""

    BOOKINGS = "bookings"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    COMPLETION_RATE = "completion_rate"
    CANCELLATION_RATE = "cancellation_rate"
    NO_SHOW_RATE = "no_show_rate"
    REVENUE = "revenue"
    AVERAGE_TICKET = "average_ticket"
    COLLECTED = "collected"
    REFUNDED = "refunded"
    PREPAID_SHARE = "prepaid_share"
    UNIQUE_CUSTOMERS = "unique_customers"
    NEW_CUSTOMERS = "new_customers"
    RETURNING_CUSTOMERS = "returning_customers"
    REPEAT_RATE = "repeat_rate"
    LAPSED_CUSTOMERS = "lapsed_customers"
    UTILIZATION = "utilization"
    MARKETPLACE_SHARE = "marketplace_share"
    MEDIAN_LEAD_TIME_HOURS = "median_lead_time_hours"
    WALK_INS = "walk_ins"
    AVERAGE_QUEUE_WAIT_MINUTES = "average_queue_wait_minutes"


METRIC_UNITS: dict[MetricName, MetricUnit] = {
    MetricName.BOOKINGS: MetricUnit.COUNT,
    MetricName.COMPLETED: MetricUnit.COUNT,
    MetricName.CANCELLED: MetricUnit.COUNT,
    MetricName.NO_SHOW: MetricUnit.COUNT,
    MetricName.COMPLETION_RATE: MetricUnit.RATIO,
    MetricName.CANCELLATION_RATE: MetricUnit.RATIO,
    MetricName.NO_SHOW_RATE: MetricUnit.RATIO,
    MetricName.REVENUE: MetricUnit.MONEY,
    MetricName.AVERAGE_TICKET: MetricUnit.MONEY,
    MetricName.COLLECTED: MetricUnit.MONEY,
    MetricName.REFUNDED: MetricUnit.MONEY,
    MetricName.PREPAID_SHARE: MetricUnit.RATIO,
    MetricName.UNIQUE_CUSTOMERS: MetricUnit.COUNT,
    MetricName.NEW_CUSTOMERS: MetricUnit.COUNT,
    MetricName.RETURNING_CUSTOMERS: MetricUnit.COUNT,
    MetricName.REPEAT_RATE: MetricUnit.RATIO,
    MetricName.LAPSED_CUSTOMERS: MetricUnit.COUNT,
    MetricName.UTILIZATION: MetricUnit.RATIO,
    MetricName.MARKETPLACE_SHARE: MetricUnit.RATIO,
    MetricName.MEDIAN_LEAD_TIME_HOURS: MetricUnit.HOURS,
    MetricName.WALK_INS: MetricUnit.COUNT,
    MetricName.AVERAGE_QUEUE_WAIT_MINUTES: MetricUnit.MINUTES,
}


class ChartId(StrEnum):
    BOOKINGS_TREND = "bookings_trend"
    REVENUE_TREND = "revenue_trend"
    BOOKING_OUTCOMES = "booking_outcomes"
    REVENUE_BY_SERVICE = "revenue_by_service"
    REVENUE_BY_PROVIDER = "revenue_by_provider"
    REVENUE_BY_LOCATION = "revenue_by_location"
    SOURCE_MIX = "source_mix"
    NEW_VS_RETURNING = "new_vs_returning"
    RETENTION_COHORTS = "retention_cohorts"
    PEAK_HOURS = "peak_hours"
    PROVIDER_UTILIZATION = "provider_utilization"
    BOOKINGS_FORECAST = "bookings_forecast"
    QUEUE_WAIT_TIMES = "queue_wait_times"
    PAYOUTS_BREAKDOWN = "payouts_breakdown"
    NOVA_CHARGES = "nova_charges"
    COMMISSION_BY_CLASS = "commission_by_class"


class ChartKind(StrEnum):
    BAR = "bar"
    STACKED_BAR = "stacked_bar"
    COMBO = "combo"
    DONUT = "donut"
    HEATMAP = "heatmap"
    FORECAST = "forecast"


@dataclass(frozen=True)
class ChartDefinition:
    chart_id: ChartId
    kind: ChartKind
    title_en: str
    title_ar: str
    question_en: str
    question_ar: str
    required_feature: str | None = None

    def title(self, locale: str) -> str:
        return self.title_ar if locale == "ar" else self.title_en

    def question(self, locale: str) -> str:
        return self.question_ar if locale == "ar" else self.question_en


def _chart(
    chart_id: ChartId,
    kind: ChartKind,
    title: tuple[str, str],
    question: tuple[str, str],
    required_feature: str | None = None,
) -> tuple[ChartId, ChartDefinition]:
    return chart_id, ChartDefinition(
        chart_id=chart_id,
        kind=kind,
        title_en=title[0],
        title_ar=title[1],
        question_en=question[0],
        question_ar=question[1],
        required_feature=required_feature,
    )


#: The chart catalog, docs/13 section 7, in the order a dashboard lists it.
CHARTS: dict[ChartId, ChartDefinition] = dict(
    [
        _chart(
            ChartId.BOOKINGS_TREND,
            ChartKind.STACKED_BAR,
            ("Bookings and how they ended", "الحجوزات ونتائجها"),
            (
                "How many bookings per period, and how did they end?",
                "كم عدد الحجوزات في كل فترة، وكيف انتهت؟",
            ),
        ),
        _chart(
            ChartId.REVENUE_TREND,
            ChartKind.COMBO,
            ("Revenue from completed bookings", "إيرادات الحجوزات المكتملة"),
            (
                "What did completed bookings earn per period?",
                "كم حققت الحجوزات المكتملة من إيرادات في كل فترة؟",
            ),
        ),
        _chart(
            ChartId.BOOKING_OUTCOMES,
            ChartKind.DONUT,
            ("Booking outcomes", "نتائج الحجوزات"),
            (
                "What share completed, cancelled or no-showed?",
                "ما نسبة الحجوزات المكتملة والملغاة والتي لم يحضر أصحابها؟",
            ),
        ),
        _chart(
            ChartId.REVENUE_BY_SERVICE,
            ChartKind.BAR,
            ("Revenue by service", "الإيرادات حسب الخدمة"),
            ("Which services earn most?", "ما الخدمات الأعلى إيرادًا؟"),
        ),
        _chart(
            ChartId.REVENUE_BY_PROVIDER,
            ChartKind.BAR,
            ("Revenue by provider", "الإيرادات حسب مقدّم الخدمة"),
            ("Which providers earn most?", "من مقدّمو الخدمة الأعلى إيرادًا؟"),
        ),
        _chart(
            ChartId.REVENUE_BY_LOCATION,
            ChartKind.BAR,
            ("Revenue by branch", "الإيرادات حسب الفرع"),
            ("How do branches compare?", "كيف تتقارن الفروع؟"),
            required_feature=CROSS_LOCATION_FEATURE,
        ),
        _chart(
            ChartId.SOURCE_MIX,
            ChartKind.DONUT,
            ("Where bookings come from", "مصادر الحجوزات"),
            ("Where do bookings come from?", "من أين تأتي الحجوزات؟"),
        ),
        _chart(
            ChartId.NEW_VS_RETURNING,
            ChartKind.STACKED_BAR,
            ("New and returning customers", "العملاء الجدد والعائدون"),
            (
                "Is the business growing, or retaining?",
                "هل ينمو النشاط أم يحافظ على عملائه؟",
            ),
        ),
        _chart(
            ChartId.RETENTION_COHORTS,
            ChartKind.HEATMAP,
            (
                "Customer retention by first-visit month",
                "الاحتفاظ بالعملاء حسب شهر الزيارة الأولى",
            ),
            ("Do first-time customers come back?", "هل يعود العملاء بعد زيارتهم الأولى؟"),
        ),
        _chart(
            ChartId.PEAK_HOURS,
            ChartKind.HEATMAP,
            ("Busiest hours", "أوقات الذروة"),
            ("When are the busiest hours?", "متى تكون أكثر الأوقات ازدحامًا؟"),
        ),
        _chart(
            ChartId.PROVIDER_UTILIZATION,
            ChartKind.BAR,
            ("Provider utilization", "نسبة إشغال مقدّمي الخدمة"),
            (
                "Who is over- or under-booked?",
                "من المشغول أكثر من اللازم أو أقل منه؟",
            ),
        ),
        _chart(
            ChartId.BOOKINGS_FORECAST,
            ChartKind.FORECAST,
            ("Weekly bookings trend", "اتجاه الحجوزات الأسبوعية"),
            ("Where are weekly bookings heading?", "إلى أين تتجه الحجوزات الأسبوعية؟"),
        ),
        _chart(
            ChartId.QUEUE_WAIT_TIMES,
            ChartKind.COMBO,
            ("Walk-in waiting times", "أوقات انتظار الحضور المباشر"),
            ("How long do walk-ins wait?", "كم ينتظر عملاء الحضور المباشر؟"),
        ),
        _chart(
            ChartId.PAYOUTS_BREAKDOWN,
            ChartKind.STACKED_BAR,
            ("Payouts and deductions", "المدفوعات والخصومات"),
            (
                "What was paid out, and what was deducted?",
                "ما الذي تم دفعه وما الذي تم خصمه؟",
            ),
        ),
        _chart(
            ChartId.NOVA_CHARGES,
            ChartKind.STACKED_BAR,
            ("NOVA charges by month", "رسوم نوفا الشهرية"),
            ("What did NOVA invoice each month?", "كم فوترت نوفا في كل شهر؟"),
        ),
        _chart(
            ChartId.COMMISSION_BY_CLASS,
            ChartKind.BAR,
            ("Commission by class", "العمولة حسب الفئة"),
            ("Why is commission what it is?", "لماذا العمولة بهذا المقدار؟"),
        ),
    ]
)


def parse_chart_id(value: str) -> ChartId:
    """A chart id from a path or an agent's tool call; unknown names are a 404."""
    try:
        return ChartId(value)
    except ValueError as exc:
        raise UnknownChartError(value) from exc


#: Bilingual names for `BookingSource` values, for breakdowns and charts.
SOURCE_LABELS: dict[str, tuple[str, str]] = {
    "marketplace": ("NOVA marketplace", "سوق نوفا"),
    "direct_link": ("Your booking link", "رابط الحجز الخاص بك"),
    "whatsapp": ("WhatsApp", "واتساب"),
    "walk_in": ("Walk-in", "حضور مباشر"),
    "reception": ("Reception", "الاستقبال"),
    "ai_agent": ("AI assistant", "المساعد الذكي"),
}


# --- the report window ------------------------------------------------------


@dataclass(frozen=True)
class ReportWindow:
    """Local calendar dates, both inclusive, and the UTC instants they cover.

    A local day starts at local midnight (ADR-0007): "August" in Riyadh does
    not begin at 00:00 UTC, which is 03:00 there.
    """

    date_from: date
    date_to: date
    timezone: str

    @property
    def days(self) -> int:
        return (self.date_to - self.date_from).days + 1

    @property
    def starts_at(self) -> datetime:
        return _local_midnight(self.date_from, self.timezone)

    @property
    def ends_at(self) -> datetime:
        return _local_midnight(self.date_to + timedelta(days=1), self.timezone)


def _local_midnight(day: date, timezone: str) -> datetime:
    return datetime.combine(day, time.min, tzinfo=ZoneInfo(timezone)).astimezone(UTC)


def build_window(
    *,
    date_from: date | None,
    date_to: date | None,
    timezone: str,
    today: date,
) -> ReportWindow:
    """Defaults to the last 30 days ending today, and refuses anything unbounded."""
    end = date_to or today
    start = date_from or end - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    if end < start:
        raise ReportWindowError("date_to must not be before date_from.")
    window = ReportWindow(date_from=start, date_to=end, timezone=timezone)
    if window.days > MAX_WINDOW_DAYS:
        raise ReportWindowError(
            f"A report covers at most {MAX_WINDOW_DAYS} days; this one asks for {window.days}."
        )
    return window


def resolve_granularity(window: ReportWindow, requested: Granularity | None) -> Granularity:
    """Day up to 45 days, week up to 180, month beyond (docs/13 section 6.3)."""
    if requested is not None:
        return requested
    if window.days <= 45:
        return Granularity.DAY
    if window.days <= 180:
        return Granularity.WEEK
    return Granularity.MONTH


# --- result values ----------------------------------------------------------


@dataclass(frozen=True)
class Kpi:
    """One metric. `value` is None exactly when `suppressed` is True."""

    metric: MetricName
    value: Decimal | None
    unit: MetricUnit
    sample_size: int
    suppressed: bool = False


@dataclass(frozen=True)
class BreakdownRow:
    key: str
    label_en: str
    label_ar: str
    bookings: int
    completed: int
    revenue: Decimal
    share_of_revenue: Decimal | None


@dataclass(frozen=True)
class ForecastPoint:
    week_start: date
    value: Decimal
    lower: Decimal | None
    upper: Decimal | None
    is_forecast: bool


@dataclass(frozen=True)
class Forecast:
    metric: ForecastMetric
    points: tuple[ForecastPoint, ...]
    slope_per_week: Decimal
    history_weeks: int


@dataclass(frozen=True)
class FinancialSummary:
    """The accountant's ledger for one window (docs/13 section 6.4)."""

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


@dataclass(frozen=True)
class ChartSpec:
    """A built chart. `figure` is Plotly's own JSON: `data` plus `layout`."""

    chart_id: ChartId
    kind: ChartKind
    title: str
    description: str
    locale: str
    figure: dict[str, Any]
    data_points: int


__all__ = [
    "CHARTS",
    "CROSS_LOCATION_FEATURE",
    "MAX_FACT_ROWS",
    "METRIC_UNITS",
    "SOURCE_LABELS",
    "BreakdownRow",
    "ChartDefinition",
    "ChartId",
    "ChartKind",
    "ChartSpec",
    "Dimension",
    "FinancialSummary",
    "Forecast",
    "ForecastMetric",
    "ForecastPoint",
    "Granularity",
    "Kpi",
    "MetricName",
    "MetricUnit",
    "ReportWindow",
    "build_window",
    "parse_chart_id",
    "resolve_granularity",
]
