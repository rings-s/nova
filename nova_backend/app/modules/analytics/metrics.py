"""analytics · COMPUTATION — pandas and numpy over fact frames.

Layer rule: pure. No I/O, no FastAPI, no SQLAlchemy: facts in, values out.
numpy and pandas are imported here and in no other file (plotly lives in
`charts.py`); `tests/test_architecture.py` enforces it.

Money sums never pass through a float. Amounts arrive as int64 fils, are summed
as integers and leave as Decimal through `_money` (docs/06 section 8). The one
float in sight is the forecast's regression, which is an estimate by nature and
is rounded back to fils on the way out.
"""

from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import numpy as np
import pandas as pd

from app.core.values import to_minor_units
from app.modules.analytics.domain import (
    LAPSED_AFTER_DAYS,
    LAPSED_UNTIL_DAYS,
    MAX_FORECAST_HISTORY_WEEKS,
    METRIC_UNITS,
    MIN_COHORT_SIZE,
    MIN_FORECAST_WEEKS,
    MIN_SAMPLE,
    BreakdownRow,
    Dimension,
    FinancialSummary,
    Forecast,
    ForecastMetric,
    ForecastPoint,
    Granularity,
    Kpi,
    MetricName,
    ReportWindow,
)
from app.modules.analytics.exceptions import InsufficientDataError
from app.modules.billing.domain import CommissionLine, Invoice, InvoiceStatus, Payout
from app.modules.booking.domain import (
    BookingFact,
    BookingSource,
    BookingStatus,
    CustomerVisitFact,
    ProviderCapacityFact,
)
from app.modules.payment.domain import PaymentFact, PaymentStatus
from app.modules.queue.domain import QueueEntryFact

_CENT = Decimal("0.01")
_RATIO = Decimal("0.0001")

#: Time a provider was genuinely spoken for. A no-show did occupy the slot, but
#: counting it would make an unreliable clientele look like a busy provider.
_BOOKED_STATUSES = frozenset(
    {
        BookingStatus.COMPLETED,
        BookingStatus.IN_SERVICE,
        BookingStatus.CHECKED_IN,
        BookingStatus.CONFIRMED,
        BookingStatus.PENDING_PAYMENT,
    }
)
_SETTLED_PAYMENTS = frozenset({PaymentStatus.CAPTURED, PaymentStatus.PARTIALLY_REFUNDED})

OUTCOMES = ("completed", "cancelled", "no_show", "upcoming")


# --- small exact helpers ----------------------------------------------------


def _money(minor: int | np.integer) -> Decimal:
    return (Decimal(int(minor)) / 100).quantize(_CENT)


def _average_money(total_minor: int, count: int) -> Decimal | None:
    if count == 0:
        return None
    return (Decimal(total_minor) / count / 100).quantize(_CENT, rounding=ROUND_HALF_UP)


def _ratio(numerator: int, denominator: int, *, minimum: int = MIN_SAMPLE) -> Decimal | None:
    """A share, or None when the sample is too small to mean anything."""
    if denominator == 0 or denominator < minimum:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(_RATIO, rounding=ROUND_HALF_UP)


def _one_decimal(value: float) -> Decimal:
    return Decimal(str(round(value, 1)))


def _kpi(metric: MetricName, value: Decimal | None, sample_size: int) -> Kpi:
    return Kpi(
        metric=metric,
        value=value,
        unit=METRIC_UNITS[metric],
        sample_size=sample_size,
        suppressed=value is None,
    )


def _between(series: pd.Series, window: ReportWindow) -> pd.Series:
    return (series >= window.starts_at) & (series < window.ends_at)


def primary_currency(currencies: Iterable[str], *, default: str = "SAR") -> str:
    """The currency most rows are in. NOVA is SAR-only, so this is nearly always SAR."""
    counts = pd.Series(list(currencies), dtype="object").value_counts()
    return str(counts.index[0]) if not counts.empty else default


# --- frames -----------------------------------------------------------------

_BOOKING_COLUMNS = [
    "id",
    "location_id",
    "service_id",
    "provider_id",
    "customer_id",
    "starts_at",
    "ends_at",
    "created_at",
    "status",
    "source",
    "price_minor",
    "currency",
]


def _frame(rows: list[dict[str, Any]], columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=columns)


def _utc(frame: pd.DataFrame, *columns: str) -> pd.DataFrame:
    for column in columns:
        frame[column] = pd.to_datetime(frame[column], utc=True)
    return frame


def _one_currency(frame: pd.DataFrame, currency: str) -> tuple[pd.DataFrame, int]:
    keep = frame["currency"] == currency
    return frame[keep].reset_index(drop=True), int((~keep).sum())


def booking_frame(facts: Sequence[BookingFact], *, currency: str) -> tuple[pd.DataFrame, int]:
    """Bookings in one currency, and how many rows in another were set aside."""
    frame = _frame(
        [
            {
                "id": str(f.id),
                "location_id": str(f.location_id),
                "service_id": str(f.service_id),
                "provider_id": str(f.provider_id),
                "customer_id": str(f.customer_id),
                "starts_at": f.starts_at,
                "ends_at": f.ends_at,
                "created_at": f.created_at,
                "status": str(f.status),
                "source": str(f.source),
                "price_minor": f.price_minor,
                "currency": f.currency,
            }
            for f in facts
        ],
        _BOOKING_COLUMNS,
    )
    frame["price_minor"] = frame["price_minor"].astype("int64")
    return _one_currency(_utc(frame, "starts_at", "ends_at", "created_at"), currency)


def payment_frame(facts: Sequence[PaymentFact], *, currency: str) -> tuple[pd.DataFrame, int]:
    frame = _frame(
        [
            {
                "booking_id": str(f.booking_id),
                "status": str(f.status),
                "amount_minor": f.amount_minor,
                "refunded_minor": f.refunded_minor,
                "currency": f.currency,
                "captured_at": f.captured_at,
                "refunded_at": f.refunded_at,
            }
            for f in facts
        ],
        [
            "booking_id",
            "status",
            "amount_minor",
            "refunded_minor",
            "currency",
            "captured_at",
            "refunded_at",
        ],
    )
    frame[["amount_minor", "refunded_minor"]] = frame[["amount_minor", "refunded_minor"]].astype(
        "int64"
    )
    return _one_currency(_utc(frame, "captured_at", "refunded_at"), currency)


def visit_frame(facts: Sequence[CustomerVisitFact]) -> pd.DataFrame:
    frame = _frame(
        [
            {
                "customer_id": str(f.customer_id),
                "first_completed_at": f.first_completed_at,
                "last_completed_at": f.last_completed_at,
                "completed_count": f.completed_count,
                "has_upcoming": f.has_upcoming,
            }
            for f in facts
        ],
        [
            "customer_id",
            "first_completed_at",
            "last_completed_at",
            "completed_count",
            "has_upcoming",
        ],
    )
    frame["has_upcoming"] = frame["has_upcoming"].astype(bool)
    return _utc(frame, "first_completed_at", "last_completed_at")


def queue_frame(facts: Sequence[QueueEntryFact]) -> pd.DataFrame:
    frame = _frame(
        [
            {
                "location_id": str(f.location_id),
                "source": str(f.source),
                "status": str(f.status),
                "joined_at": f.joined_at,
                "called_at": f.called_at,
            }
            for f in facts
        ],
        ["location_id", "source", "status", "joined_at", "called_at"],
    )
    return _utc(frame, "joined_at", "called_at")


# --- periods ----------------------------------------------------------------


def bucket(series: pd.Series, *, timezone: str, granularity: Granularity) -> pd.Series:
    """Each instant's period start, as a local calendar date (weeks start Monday)."""
    local = series.dt.tz_convert(timezone).dt.tz_localize(None).dt.normalize()
    if granularity is Granularity.WEEK:
        local = local - pd.to_timedelta(local.dt.weekday, unit="D")
    elif granularity is Granularity.MONTH:
        local = local.dt.to_period("M").dt.to_timestamp()
    return local.dt.date


def period_starts(window: ReportWindow, granularity: Granularity) -> list[date]:
    """Every period the window touches, so a quiet week shows as zero, not as a gap."""
    days = pd.date_range(window.date_from, window.date_to, freq="D")
    if granularity is Granularity.WEEK:
        days = (days - pd.to_timedelta(days.weekday, unit="D")).unique()
    elif granularity is Granularity.MONTH:
        days = days.to_period("M").to_timestamp().unique()
    return [ts.date() for ts in days]


def _count_table(
    rows: pd.Series, columns: pd.Series, *, index: list[Any], names: Sequence[Any]
) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(0, index=index, columns=list(names), dtype="int64")
    table = pd.crosstab(rows, columns)
    return table.reindex(index=index, columns=list(names), fill_value=0).astype("int64")


# --- KPIs (docs/13 section 6.4) ---------------------------------------------


def booking_kpis(bookings: pd.DataFrame) -> list[Kpi]:
    status = bookings["status"]
    total = len(bookings)
    completed_mask = status == BookingStatus.COMPLETED
    completed = int(completed_mask.sum())
    cancelled = int((status == BookingStatus.CANCELLED).sum())
    no_show = int((status == BookingStatus.NO_SHOW).sum())
    resolved = completed + cancelled + no_show
    revenue_minor = int(bookings.loc[completed_mask, "price_minor"].sum())
    marketplace = int((bookings["source"] == BookingSource.MARKETPLACE).sum())

    median_lead = None
    if total >= MIN_SAMPLE:
        lead_hours = (bookings["starts_at"] - bookings["created_at"]).dt.total_seconds() / 3600
        median_lead = _one_decimal(float(lead_hours.median()))

    return [
        _kpi(MetricName.BOOKINGS, Decimal(total), total),
        _kpi(MetricName.COMPLETED, Decimal(completed), total),
        _kpi(MetricName.CANCELLED, Decimal(cancelled), total),
        _kpi(MetricName.NO_SHOW, Decimal(no_show), total),
        _kpi(MetricName.COMPLETION_RATE, _ratio(completed, resolved), resolved),
        _kpi(MetricName.CANCELLATION_RATE, _ratio(cancelled, resolved), resolved),
        _kpi(MetricName.NO_SHOW_RATE, _ratio(no_show, resolved), resolved),
        _kpi(MetricName.REVENUE, _money(revenue_minor), completed),
        _kpi(MetricName.AVERAGE_TICKET, _average_money(revenue_minor, completed), completed),
        _kpi(MetricName.MARKETPLACE_SHARE, _ratio(marketplace, total), total),
        _kpi(MetricName.MEDIAN_LEAD_TIME_HOURS, median_lead, total),
    ]


def payment_kpis(payments: pd.DataFrame, bookings: pd.DataFrame, window: ReportWindow) -> list[Kpi]:
    """Money in, for this business's bookings.

    `payments` may reach back before the window: a booking completed in August
    may have been prepaid in July, and `prepaid_share` has to see that. Only
    `collected` and `refunded` are confined to the window.
    """
    settled = payments["status"].isin([str(s) for s in _SETTLED_PAYMENTS])
    captured = settled & _between(payments["captured_at"], window)
    collected_minor = int(
        (payments.loc[captured, "amount_minor"] - payments.loc[captured, "refunded_minor"]).sum()
    )
    refunded_in_window = _between(payments["refunded_at"], window)
    refunded_minor = int(payments.loc[refunded_in_window, "refunded_minor"].sum())

    completed_ids = set(bookings.loc[bookings["status"] == BookingStatus.COMPLETED, "id"])
    prepaid = len(completed_ids & set(payments.loc[settled, "booking_id"]))

    return [
        _kpi(MetricName.COLLECTED, _money(collected_minor), int(captured.sum())),
        _kpi(MetricName.REFUNDED, _money(refunded_minor), int(refunded_in_window.sum())),
        _kpi(MetricName.PREPAID_SHARE, _ratio(prepaid, len(completed_ids)), len(completed_ids)),
    ]


def customer_kpis(bookings: pd.DataFrame, visits: pd.DataFrame, window: ReportWindow) -> list[Kpi]:
    completed = bookings[bookings["status"] == BookingStatus.COMPLETED]
    customers = set(completed["customer_id"])
    unique = len(customers)

    first = visits.set_index("customer_id")["first_completed_at"]
    new = len(customers & set(first[_between(first, window)].index))
    returning = unique - new

    last = visits["last_completed_at"]
    lapsed = int(
        (
            (last >= window.ends_at - timedelta(days=LAPSED_UNTIL_DAYS))
            & (last < window.ends_at - timedelta(days=LAPSED_AFTER_DAYS))
            & ~visits["has_upcoming"]
        ).sum()
    )

    return [
        _kpi(MetricName.UNIQUE_CUSTOMERS, Decimal(unique), unique),
        _kpi(MetricName.NEW_CUSTOMERS, Decimal(new), unique),
        _kpi(MetricName.RETURNING_CUSTOMERS, Decimal(returning), unique),
        _kpi(MetricName.REPEAT_RATE, _ratio(returning, unique), unique),
        _kpi(MetricName.LAPSED_CUSTOMERS, Decimal(lapsed), len(visits)),
    ]


def scheduled_minutes(fact: ProviderCapacityFact, window: ReportWindow) -> int:
    """Minutes a provider was rostered across the window's local dates.

    The weekly pattern is laid over the calendar with numpy, then each dated
    exception replaces its whole day, closed or open, as it does for
    availability (booking domain, `windows_for_date`).
    """
    days = pd.date_range(window.date_from, window.date_to, freq="D")
    per_weekday = np.zeros(7, dtype=np.int64)
    for weekly in fact.weekly:
        per_weekday[weekly.weekday] += weekly.duration_minutes
    minutes = per_weekday[days.weekday.to_numpy()]

    positions = {ts.date(): i for i, ts in enumerate(days)}
    for exception in fact.exceptions:
        position = positions.get(exception.on_date)
        if position is not None:
            minutes[position] = sum(w.duration_minutes for w in exception.windows)
    return int(minutes.sum())


def utilization_frame(
    bookings: pd.DataFrame, capacity: Sequence[ProviderCapacityFact], window: ReportWindow
) -> pd.DataFrame:
    booked = bookings[bookings["status"].isin([str(s) for s in _BOOKED_STATUSES])]
    booked_minutes = (
        ((booked["ends_at"] - booked["starts_at"]).dt.total_seconds() / 60)
        .groupby(booked["provider_id"])
        .sum()
    )
    frame = _frame(
        [
            {"provider_id": str(f.provider_id), "scheduled_minutes": scheduled_minutes(f, window)}
            for f in capacity
        ],
        ["provider_id", "scheduled_minutes"],
    )
    frame["booked_minutes"] = (
        frame["provider_id"].map(booked_minutes).fillna(0).round().astype("int64")
    )
    scheduled = frame["scheduled_minutes"].astype("int64")
    frame["utilization"] = (frame["booked_minutes"] / scheduled.where(scheduled > 0)).astype(float)
    return frame.sort_values("utilization", ascending=False, na_position="last").reset_index(
        drop=True
    )


def utilization_kpi(frame: pd.DataFrame) -> Kpi:
    scheduled = int(frame["scheduled_minutes"].sum())
    booked = int(frame["booked_minutes"].sum())
    value = _ratio(booked, scheduled, minimum=1)
    return _kpi(MetricName.UTILIZATION, value, scheduled)


def _wait_minutes(queue: pd.DataFrame) -> pd.Series:
    return (queue["called_at"] - queue["joined_at"]).dt.total_seconds() / 60


def queue_kpis(queue: pd.DataFrame) -> list[Kpi]:
    waits = _wait_minutes(queue).dropna()
    called = len(waits)
    average = _one_decimal(float(waits.mean())) if called >= MIN_SAMPLE else None
    return [
        _kpi(MetricName.WALK_INS, Decimal(len(queue)), len(queue)),
        _kpi(MetricName.AVERAGE_QUEUE_WAIT_MINUTES, average, called),
    ]


# --- breakdowns and series --------------------------------------------------


def breakdown(
    bookings: pd.DataFrame,
    dimension: Dimension,
    labels: dict[str, tuple[str, str]],
) -> list[BreakdownRow]:
    """Bookings, completions and completed revenue per service, provider, branch or source."""
    if bookings.empty:
        return []
    key = "source" if dimension is Dimension.SOURCE else f"{dimension}_id"
    is_completed = bookings["status"] == BookingStatus.COMPLETED
    grouped = (
        bookings.assign(
            completed=is_completed.astype("int64"),
            revenue_minor=bookings["price_minor"].where(is_completed, 0),
        )
        .groupby(key)
        .agg(
            bookings=("id", "size"),
            completed=("completed", "sum"),
            revenue_minor=("revenue_minor", "sum"),
        )
        .sort_values(["revenue_minor", "bookings"], ascending=False)
    )
    total = int(grouped["revenue_minor"].sum())

    rows: list[BreakdownRow] = []
    for key_value, row in grouped.iterrows():
        label_en, label_ar = labels.get(str(key_value), (str(key_value), str(key_value)))
        revenue_minor = int(row["revenue_minor"])
        rows.append(
            BreakdownRow(
                key=str(key_value),
                label_en=label_en,
                label_ar=label_ar,
                bookings=int(row["bookings"]),
                completed=int(row["completed"]),
                revenue=_money(revenue_minor),
                share_of_revenue=_ratio(revenue_minor, total, minimum=1),
            )
        )
    return rows


def outcome_series(
    bookings: pd.DataFrame, window: ReportWindow, granularity: Granularity
) -> pd.DataFrame:
    """Bookings per period and outcome; anything not yet resolved is `upcoming`."""
    outcome = bookings["status"].where(bookings["status"].isin(OUTCOMES[:3]), "upcoming")
    periods = bucket(bookings["starts_at"], timezone=window.timezone, granularity=granularity)
    return _count_table(periods, outcome, index=period_starts(window, granularity), names=OUTCOMES)


def revenue_series(
    bookings: pd.DataFrame, window: ReportWindow, granularity: Granularity
) -> pd.DataFrame:
    """Completed revenue (fils) and completions per period."""
    index = period_starts(window, granularity)
    completed = bookings[bookings["status"] == BookingStatus.COMPLETED]
    if completed.empty:
        return pd.DataFrame(0, index=index, columns=["revenue_minor", "completed"], dtype="int64")
    periods = bucket(completed["starts_at"], timezone=window.timezone, granularity=granularity)
    grouped = completed["price_minor"].groupby(periods).agg(["sum", "count"])
    grouped.columns = ["revenue_minor", "completed"]
    return grouped.reindex(index, fill_value=0).astype("int64")


def new_vs_returning_series(
    bookings: pd.DataFrame,
    visits: pd.DataFrame,
    window: ReportWindow,
    granularity: Granularity,
) -> pd.DataFrame:
    """Distinct customers per period, split by whether that period held their first visit."""
    index = period_starts(window, granularity)
    completed = bookings[bookings["status"] == BookingStatus.COMPLETED]
    if completed.empty:
        return pd.DataFrame(0, index=index, columns=["new", "returning"], dtype="int64")

    first = visits.set_index("customer_id")["first_completed_at"]
    frame = pd.DataFrame(
        {
            "customer_id": completed["customer_id"],
            "period": bucket(
                completed["starts_at"], timezone=window.timezone, granularity=granularity
            ),
            "first_period": bucket(
                pd.to_datetime(completed["customer_id"].map(first), utc=True),
                timezone=window.timezone,
                granularity=granularity,
            ),
        }
    ).drop_duplicates(["period", "customer_id"])
    kind = (frame["period"] == frame["first_period"]).map({True: "new", False: "returning"})
    return _count_table(frame["period"], kind, index=index, names=["new", "returning"])


def retention_matrix(
    bookings: pd.DataFrame, visits: pd.DataFrame, window: ReportWindow
) -> pd.DataFrame:
    """Share of each first-visit month's customers active N months later.

    Rows are cohort months (first-ever visit inside the window), columns are
    months since that visit. A cohort smaller than `MIN_COHORT_SIZE` is blanked:
    two customers returning is a rumour about two people, not a rate.
    """
    first = visits.set_index("customer_id")["first_completed_at"]
    first = first[_between(first, window)]
    completed = bookings[
        (bookings["status"] == BookingStatus.COMPLETED) & bookings["customer_id"].isin(first.index)
    ]
    if completed.empty:
        return pd.DataFrame()

    def _month(series: pd.Series) -> pd.Series:
        return series.dt.tz_convert(window.timezone).dt.tz_localize(None)

    activity = _month(completed["starts_at"])
    cohort = _month(pd.to_datetime(completed["customer_id"].map(first), utc=True))
    frame = pd.DataFrame(
        {
            "customer_id": completed["customer_id"],
            "cohort": cohort.dt.to_period("M").dt.to_timestamp().dt.date,
            "months_since": (activity.dt.year - cohort.dt.year) * 12
            + (activity.dt.month - cohort.dt.month),
        }
    )
    active = (
        frame.groupby(["cohort", "months_since"])["customer_id"].nunique().unstack(fill_value=0)
    )
    sizes = (
        _month(first)
        .dt.to_period("M")
        .dt.to_timestamp()
        .dt.date.value_counts()
        .reindex(active.index)
    )
    matrix = active.div(sizes, axis=0).astype(float)
    matrix[sizes < MIN_COHORT_SIZE] = np.nan
    return matrix.sort_index()


def peak_hours_matrix(
    bookings: pd.DataFrame, location_timezones: dict[str, str], *, default_timezone: str
) -> pd.DataFrame:
    """Booking starts by local weekday (rows, Monday first) and hour (columns).

    Each branch in its own timezone. Cancelled bookings are left out: they were
    demand once, but nobody sat in the chair.
    """
    matrix = pd.DataFrame(0, index=range(7), columns=range(24), dtype="int64")
    live = bookings[bookings["status"] != BookingStatus.CANCELLED]
    for location_id, group in live.groupby("location_id"):
        local = group["starts_at"].dt.tz_convert(
            location_timezones.get(str(location_id), default_timezone)
        )
        counts = pd.crosstab(local.dt.weekday, local.dt.hour)
        matrix = matrix.add(
            counts.reindex(index=range(7), columns=range(24), fill_value=0), fill_value=0
        )
    return matrix.astype("int64")


def queue_wait_series(
    queue: pd.DataFrame, window: ReportWindow, granularity: Granularity
) -> pd.DataFrame:
    index = period_starts(window, granularity)
    if queue.empty:
        return pd.DataFrame({"walk_ins": 0, "average_wait_minutes": np.nan}, index=index).astype(
            {"walk_ins": "int64"}
        )
    periods = bucket(queue["joined_at"], timezone=window.timezone, granularity=granularity)
    grouped = pd.DataFrame(
        {
            "walk_ins": queue["joined_at"].groupby(periods).size(),
            "average_wait_minutes": _wait_minutes(queue).groupby(periods).mean(),
        }
    )
    frame = grouped.reindex(index)
    frame["walk_ins"] = frame["walk_ins"].fillna(0).astype("int64")
    return frame


# --- forecast (docs/13 section 10) ------------------------------------------


def weekly_history(
    bookings: pd.DataFrame, *, metric: ForecastMetric, timezone: str, as_of: datetime
) -> pd.Series:
    """Complete weeks only, oldest first, quiet weeks as zero, at most 26."""
    frame = (
        bookings
        if metric is ForecastMetric.BOOKINGS
        else bookings[bookings["status"] == BookingStatus.COMPLETED]
    )
    if frame.empty:
        return pd.Series(dtype="int64")
    weeks = bucket(frame["starts_at"], timezone=timezone, granularity=Granularity.WEEK)
    values = (
        frame["price_minor"]
        if metric is ForecastMetric.REVENUE
        else pd.Series(1, index=frame.index, dtype="int64")
    )
    totals = values.groupby(weeks).sum()

    local_today = pd.Timestamp(as_of).tz_convert(timezone).date()
    current_week = local_today - timedelta(days=local_today.weekday())
    first_week = min(totals.index)
    complete_weeks = [
        first_week + timedelta(weeks=i) for i in range((current_week - first_week).days // 7)
    ]
    history = totals.reindex(complete_weeks, fill_value=0).astype("int64")
    return history.iloc[-MAX_FORECAST_HISTORY_WEEKS:]


def linear_forecast(history: pd.Series, *, metric: ForecastMetric, horizon_weeks: int) -> Forecast:
    """Least-squares trend with a band of 1.96 residual standard deviations, floored at zero.

    A trend, not a prediction: no seasonality, no holidays. Ramadan and Eid move
    through the calendar every year, and a straight line knows nothing of it.
    """
    if len(history) < MIN_FORECAST_WEEKS:
        raise InsufficientDataError(
            f"A trend needs at least {MIN_FORECAST_WEEKS} complete weeks of history; "
            f"there are {len(history)}."
        )
    y = history.to_numpy(dtype=float)
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    residuals = y - (slope * x + intercept)
    band = 1.96 * float(np.std(residuals, ddof=1))

    def scaled(value: float) -> Decimal:
        if metric is ForecastMetric.REVENUE:
            return (Decimal(round(value)) / 100).quantize(_CENT)
        return _one_decimal(value)

    points = [
        ForecastPoint(
            week_start=week, value=scaled(value), lower=None, upper=None, is_forecast=False
        )
        for week, value in zip(history.index, y, strict=True)
    ]
    last_week: date = history.index[-1]
    for step in range(1, horizon_weeks + 1):
        predicted = float(slope * (len(y) - 1 + step) + intercept)
        points.append(
            ForecastPoint(
                week_start=last_week + timedelta(weeks=step),
                value=scaled(max(predicted, 0.0)),
                lower=scaled(max(predicted - band, 0.0)),
                upper=scaled(max(predicted + band, 0.0)),
                is_forecast=True,
            )
        )
    return Forecast(
        metric=metric,
        points=tuple(points),
        slope_per_week=scaled(float(slope)),
        history_weeks=len(y),
    )


# --- the ledger (the accountant's view) -------------------------------------


def payouts_frame(payouts: Sequence[Payout], *, currency: str) -> pd.DataFrame:
    frame = _frame(
        [
            {
                "payout_date": p.payout_date,
                "collected_minor": to_minor_units(p.collected_amount.amount),
                "processing_minor": to_minor_units(p.processing_fee.amount),
                "commission_minor": to_minor_units(p.commission_netted.amount),
                "net_minor": to_minor_units(p.net_amount),
            }
            for p in payouts
            if p.collected_amount.currency == currency
        ],
        ["payout_date", "collected_minor", "processing_minor", "commission_minor", "net_minor"],
    )
    return frame.groupby("payout_date").sum().astype("int64").sort_index()


def invoices_frame(invoices: Sequence[Invoice], *, currency: str) -> pd.DataFrame:
    frame = _frame(
        [
            {
                "period_start": i.period.period_start,
                "status": str(i.status),
                "subscription_minor": to_minor_units(i.subscription_amount),
                "commission_minor": to_minor_units(i.commission_amount),
                "processing_minor": to_minor_units(i.processing_amount),
                "vat_minor": to_minor_units(i.vat_amount),
                "total_minor": to_minor_units(i.total_amount),
            }
            for i in invoices
            if i.currency == currency
        ],
        [
            "period_start",
            "status",
            "subscription_minor",
            "commission_minor",
            "processing_minor",
            "vat_minor",
            "total_minor",
        ],
    )
    return frame.sort_values("period_start").reset_index(drop=True)


def commission_by_class(lines: Sequence[CommissionLine], *, currency: str) -> pd.DataFrame:
    """Commission per class, with each reversal counted against its class."""
    frame = _frame(
        [
            {
                "commission_class": str(line.commission_class),
                "signed_minor": to_minor_units(line.signed_amount),
                "is_reversal": line.is_reversal,
            }
            for line in lines
            if line.amount.currency == currency
        ],
        ["commission_class", "signed_minor", "is_reversal"],
    )
    if frame.empty:
        return pd.DataFrame(columns=["signed_minor", "lines"]).astype("int64")
    return (
        frame.groupby("commission_class")
        .agg(signed_minor=("signed_minor", "sum"), lines=("signed_minor", "size"))
        .astype("int64")
    )


def financial_summary(
    *,
    bookings: pd.DataFrame,
    payments: pd.DataFrame,
    lines: Sequence[CommissionLine],
    invoices: Sequence[Invoice],
    payouts: Sequence[Payout],
    window: ReportWindow,
    currency: str,
) -> FinancialSummary:
    kpis = {k.metric: k for k in booking_kpis(bookings) + payment_kpis(payments, bookings, window)}

    in_currency = [line for line in lines if line.amount.currency == currency]
    accrued = sum(
        (to_minor_units(line.amount.amount) for line in in_currency if not line.is_reversal), 0
    )
    reversed_ = sum(
        (to_minor_units(line.amount.amount) for line in in_currency if line.is_reversal), 0
    )

    paid_out = payouts_frame(payouts, currency=currency).sum()
    billed = invoices_frame(invoices, currency=currency)
    outstanding = billed[
        billed["status"].isin([str(InvoiceStatus.ISSUED), str(InvoiceStatus.OVERDUE)])
    ]

    def column_total(frame: pd.DataFrame | pd.Series, name: str) -> Decimal:
        return _money(int(frame[name].sum())) if name in frame else _money(0)

    return FinancialSummary(
        currency=currency,
        revenue=kpis[MetricName.REVENUE].value or _money(0),
        collected=kpis[MetricName.COLLECTED].value or _money(0),
        refunded=kpis[MetricName.REFUNDED].value or _money(0),
        commission_accrued=_money(accrued),
        commission_reversed=_money(reversed_),
        payouts_collected=_money(int(paid_out.get("collected_minor", 0))),
        payouts_processing_fees=_money(int(paid_out.get("processing_minor", 0))),
        payouts_commission_netted=_money(int(paid_out.get("commission_minor", 0))),
        payouts_net=_money(int(paid_out.get("net_minor", 0))),
        invoiced_subscription=column_total(billed, "subscription_minor"),
        invoiced_commission=column_total(billed, "commission_minor"),
        invoiced_processing=column_total(billed, "processing_minor"),
        invoiced_vat=column_total(billed, "vat_minor"),
        invoiced_total=column_total(billed, "total_minor"),
        outstanding_invoices=len(outstanding),
        outstanding_total=column_total(outstanding, "total_minor"),
    )


__all__ = [
    "OUTCOMES",
    "booking_frame",
    "booking_kpis",
    "breakdown",
    "bucket",
    "commission_by_class",
    "customer_kpis",
    "financial_summary",
    "invoices_frame",
    "linear_forecast",
    "new_vs_returning_series",
    "outcome_series",
    "payment_frame",
    "payment_kpis",
    "payouts_frame",
    "peak_hours_matrix",
    "period_starts",
    "primary_currency",
    "queue_frame",
    "queue_kpis",
    "queue_wait_series",
    "retention_matrix",
    "revenue_series",
    "scheduled_minutes",
    "utilization_frame",
    "utilization_kpi",
    "visit_frame",
    "weekly_history",
]
