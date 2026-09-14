"""Every chart builds to plain JSON, in both languages, with no customer in it. Pure.

docs/13 section 12: "every chart id builds, serialises to JSON, contains no NaN,
uses Arabic labels for `ar`, and carries no customer id."
"""

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import cycle
from uuid import uuid4

import pandas as pd
import pytest

from app.core.values import Money
from app.modules.analytics import charts
from app.modules.analytics import metrics as m
from app.modules.analytics.domain import (
    CHARTS,
    SOURCE_LABELS,
    ChartId,
    ChartSpec,
    Dimension,
    ForecastMetric,
    Granularity,
    build_window,
)
from app.modules.billing.domain import (
    BillingPeriod,
    CommissionClass,
    CommissionLine,
    Invoice,
    InvoiceStatus,
    Payout,
)
from app.modules.booking.domain import (
    BookingFact,
    BookingSource,
    BookingStatus,
    CustomerVisitFact,
    ProviderCapacityFact,
    WorkingWindow,
)
from app.modules.queue.domain import QueueEntryFact, QueueEntrySource, QueueEntryStatus

RIYADH = "Asia/Riyadh"
WINDOW = build_window(
    date_from=date(2026, 8, 1), date_to=date(2026, 8, 31), timezone=RIYADH, today=date(2026, 9, 14)
)
STEP = Granularity.WEEK
CUSTOMER = uuid4()
TENANT, BUSINESS, LOCATION, SERVICE, PROVIDER = (uuid4() for _ in range(5))
LABELS = {
    str(SERVICE): ("Haircut", "قص شعر"),
    str(PROVIDER): ("Sara", "سارة"),
    str(LOCATION): ("Olaya", "العليا"),
}


def _at(day: int) -> datetime:
    return datetime(2026, 8, day, 7, 0, tzinfo=UTC)


_statuses = cycle(
    [
        BookingStatus.COMPLETED,
        BookingStatus.COMPLETED,
        BookingStatus.CANCELLED,
        BookingStatus.NO_SHOW,
        BookingStatus.CONFIRMED,
    ]
)
_sources = cycle(list(BookingSource))
BOOKINGS = m.booking_frame(
    [
        BookingFact(
            id=uuid4(),
            location_id=LOCATION,
            service_id=SERVICE,
            provider_id=PROVIDER,
            customer_id=CUSTOMER,
            starts_at=_at(day),
            ends_at=_at(day) + timedelta(hours=1),
            created_at=_at(day) - timedelta(days=2),
            status=next(_statuses),
            source=next(_sources),
            price_minor=17250,
            currency="SAR",
        )
        for day in range(1, 29)
    ],
    currency="SAR",
)[0]
VISITS = m.visit_frame(
    [
        CustomerVisitFact(
            customer_id=CUSTOMER,
            first_completed_at=_at(1),
            last_completed_at=_at(26),
            completed_count=12,
            has_upcoming=False,
        )
    ]
)
CAPACITY = [
    ProviderCapacityFact(
        provider_id=PROVIDER,
        weekly=tuple(WorkingWindow(weekday=d, start_minute=540, end_minute=1260) for d in range(7)),
        exceptions=(),
    )
]
QUEUE = m.queue_frame(
    [
        QueueEntryFact(
            location_id=LOCATION,
            service_id=SERVICE,
            provider_id=None,
            source=QueueEntrySource.WALK_IN,
            status=QueueEntryStatus.COMPLETED,
            party_size=1,
            joined_at=_at(day),
            called_at=_at(day) + timedelta(minutes=14),
            completed_at=None,
        )
        for day in range(1, 12)
    ]
)
HISTORY = pd.Series(
    [12, 14, 13, 16, 15, 18, 17, 19, 21, 20],
    index=[date(2026, 6, 1) + timedelta(weeks=i) for i in range(10)],
    dtype="int64",
)
LINE = CommissionLine(
    id=uuid4(),
    tenant_id=TENANT,
    business_id=BUSINESS,
    booking_id=uuid4(),
    customer_id=CUSTOMER,
    source="marketplace",
    commission_class=CommissionClass.NEW_MARKETPLACE,
    base_amount=Money(amount=Decimal("150.00")),
    rate_pct=Decimal("35"),
    amount=Money(amount=Decimal("52.50")),
)
INVOICE = Invoice(
    id=uuid4(),
    tenant_id=TENANT,
    business_id=BUSINESS,
    period=BillingPeriod(period_start=date(2026, 8, 1), period_end=date(2026, 9, 1)),
    status=InvoiceStatus.ISSUED,
    subscription_amount=Decimal("199.00"),
    commission_amount=Decimal("52.50"),
    vat_amount=Decimal("37.73"),
    total_amount=Decimal("289.23"),
)
PAYOUT = Payout(
    id=uuid4(),
    tenant_id=TENANT,
    business_id=BUSINESS,
    payout_date=date(2026, 8, 4),
    collected_amount=Money(amount=Decimal("172.50")),
    processing_fee=Money(amount=Decimal("4.31")),
    commission_netted=Money(amount=Decimal("52.50")),
)


def _ranked(dimension: Dimension) -> Callable[[str], ChartSpec]:
    builder = {
        Dimension.SERVICE: charts.revenue_by_service,
        Dimension.PROVIDER: charts.revenue_by_provider,
        Dimension.LOCATION: charts.revenue_by_location,
    }[dimension]
    return lambda locale: builder(
        m.breakdown(BOOKINGS, dimension, LABELS), locale=locale, currency="SAR"
    )


BUILDERS: dict[ChartId, Callable[[str], ChartSpec]] = {
    ChartId.BOOKINGS_TREND: lambda locale: charts.bookings_trend(
        m.outcome_series(BOOKINGS, WINDOW, STEP), locale=locale
    ),
    ChartId.REVENUE_TREND: lambda locale: charts.revenue_trend(
        m.revenue_series(BOOKINGS, WINDOW, STEP), locale=locale, currency="SAR"
    ),
    ChartId.BOOKING_OUTCOMES: lambda locale: charts.booking_outcomes(
        m.outcome_series(BOOKINGS, WINDOW, STEP), locale=locale
    ),
    ChartId.REVENUE_BY_SERVICE: _ranked(Dimension.SERVICE),
    ChartId.REVENUE_BY_PROVIDER: _ranked(Dimension.PROVIDER),
    ChartId.REVENUE_BY_LOCATION: _ranked(Dimension.LOCATION),
    ChartId.SOURCE_MIX: lambda locale: charts.source_mix(
        m.breakdown(BOOKINGS, Dimension.SOURCE, SOURCE_LABELS), locale=locale
    ),
    ChartId.NEW_VS_RETURNING: lambda locale: charts.new_vs_returning(
        m.new_vs_returning_series(BOOKINGS, VISITS, WINDOW, STEP), locale=locale
    ),
    ChartId.RETENTION_COHORTS: lambda locale: charts.retention_cohorts(
        m.retention_matrix(BOOKINGS, VISITS, WINDOW), locale=locale
    ),
    ChartId.PEAK_HOURS: lambda locale: charts.peak_hours(
        m.peak_hours_matrix(BOOKINGS, {str(LOCATION): RIYADH}, default_timezone=RIYADH),
        locale=locale,
    ),
    ChartId.PROVIDER_UTILIZATION: lambda locale: charts.provider_utilization(
        m.utilization_frame(BOOKINGS, CAPACITY, WINDOW), LABELS, locale=locale
    ),
    ChartId.BOOKINGS_FORECAST: lambda locale: charts.bookings_forecast(
        m.linear_forecast(HISTORY, metric=ForecastMetric.BOOKINGS, horizon_weeks=4), locale=locale
    ),
    ChartId.QUEUE_WAIT_TIMES: lambda locale: charts.queue_wait_times(
        m.queue_wait_series(QUEUE, WINDOW, STEP), locale=locale
    ),
    ChartId.PAYOUTS_BREAKDOWN: lambda locale: charts.payouts_breakdown(
        m.payouts_frame([PAYOUT], currency="SAR"), locale=locale, currency="SAR"
    ),
    ChartId.NOVA_CHARGES: lambda locale: charts.nova_charges(
        m.invoices_frame([INVOICE], currency="SAR"), locale=locale, currency="SAR"
    ),
    ChartId.COMMISSION_BY_CLASS: lambda locale: charts.commission_by_class(
        m.commission_by_class([LINE], currency="SAR"), locale=locale, currency="SAR"
    ),
}


def test_every_chart_in_the_catalog_has_a_builder():
    assert set(BUILDERS) == set(ChartId)


@pytest.mark.parametrize("locale", ["en", "ar"])
@pytest.mark.parametrize("chart_id", list(ChartId))
def test_every_chart_builds_to_plain_json(chart_id: ChartId, locale: str):
    spec = BUILDERS[chart_id](locale)
    # allow_nan=False raises on NaN: a JSON parser in the browser would too.
    text = json.dumps(spec.figure, allow_nan=False, ensure_ascii=False)

    assert spec.chart_id is chart_id
    assert spec.kind is CHARTS[chart_id].kind
    assert spec.title == CHARTS[chart_id].title(locale)
    assert spec.figure["data"], "a chart with no trace draws nothing"
    assert str(CUSTOMER) not in text


def test_labels_follow_the_locale():
    arabic = json.dumps(BUILDERS[ChartId.BOOKINGS_TREND]("ar").figure, ensure_ascii=False)
    english = json.dumps(BUILDERS[ChartId.BOOKINGS_TREND]("en").figure, ensure_ascii=False)
    assert "مكتملة" in arabic
    assert "Completed" not in arabic
    assert "Completed" in english


def test_names_come_from_the_bilingual_pair():
    arabic = json.dumps(BUILDERS[ChartId.REVENUE_BY_SERVICE]("ar").figure, ensure_ascii=False)
    assert "قص شعر" in arabic


def test_plotlys_own_theme_is_not_embedded():
    layout = BUILDERS[ChartId.REVENUE_TREND]("en").figure["layout"]
    assert len(json.dumps(layout.get("template", {}))) < 200
