"""The arithmetic behind every KPI and chart (docs/13 sections 6 and 10). Pure — no database."""

import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.core.values import Money, to_minor_units
from app.modules.analytics import metrics as m
from app.modules.analytics.domain import (
    Dimension,
    ForecastMetric,
    Granularity,
    Kpi,
    MetricName,
    ReportWindow,
    build_window,
)
from app.modules.analytics.exceptions import InsufficientDataError
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
    ScheduleException,
    WorkingWindow,
)
from app.modules.payment.domain import PaymentFact, PaymentStatus

RIYADH = "Asia/Riyadh"
LOCATION, SERVICE, PROVIDER = uuid4(), uuid4(), uuid4()
AUGUST = build_window(
    date_from=date(2026, 8, 1), date_to=date(2026, 8, 31), timezone=RIYADH, today=date(2026, 9, 14)
)
#: 3-9 August 2026, Monday to Sunday.
FIRST_FULL_WEEK = ReportWindow(
    date_from=date(2026, 8, 3), date_to=date(2026, 8, 9), timezone=RIYADH
)


def at(day: int, hour: int = 10, month: int = 8) -> datetime:
    """A Riyadh wall-clock time in 2026, as the UTC instant the facts carry."""
    return datetime(2026, month, day, hour, tzinfo=ZoneInfo(RIYADH)).astimezone(UTC)


def booking(
    *,
    starts_at: datetime,
    status: BookingStatus = BookingStatus.COMPLETED,
    price: str = "150.00",
    customer: UUID | None = None,
    currency: str = "SAR",
    minutes: int = 60,
    service: UUID = SERVICE,
    location: UUID = LOCATION,
) -> BookingFact:
    return BookingFact(
        id=uuid4(),
        location_id=location,
        service_id=service,
        provider_id=PROVIDER,
        customer_id=customer or uuid4(),
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=minutes),
        created_at=starts_at - timedelta(hours=24),
        status=status,
        source=BookingSource.DIRECT_LINK,
        price_minor=to_minor_units(Decimal(price)),
        currency=currency,
    )


def frame(facts: list[BookingFact]) -> pd.DataFrame:
    return m.booking_frame(facts, currency="SAR")[0]


def by_metric(kpis: list[Kpi]) -> dict[MetricName, Kpi]:
    return {kpi.metric: kpi for kpi in kpis}


def visit(customer: UUID, *, first: datetime | None, last: datetime | None, upcoming=False):
    return CustomerVisitFact(
        customer_id=customer,
        first_completed_at=first,
        last_completed_at=last,
        completed_count=1,
        has_upcoming=upcoming,
    )


class TestBookingKpis:
    def test_rates_are_over_resolved_bookings_only(self):
        statuses = (
            [BookingStatus.COMPLETED] * 16
            + [BookingStatus.CANCELLED] * 2
            + [BookingStatus.NO_SHOW] * 2
            + [BookingStatus.CONFIRMED] * 5
        )
        facts = [booking(starts_at=at(i % 28 + 1), status=s) for i, s in enumerate(statuses)]
        kpis = by_metric(m.booking_kpis(frame(facts)))

        assert kpis[MetricName.BOOKINGS].value == 25
        assert kpis[MetricName.COMPLETION_RATE].value == Decimal("0.8000")
        assert kpis[MetricName.NO_SHOW_RATE].sample_size == 20

    def test_a_rate_below_the_sample_threshold_is_suppressed_not_reported(self):
        kpis = by_metric(m.booking_kpis(frame([booking(starts_at=at(i + 1)) for i in range(19)])))
        rate = kpis[MetricName.COMPLETION_RATE]
        assert rate.value is None
        assert rate.suppressed
        assert rate.sample_size == 19
        # A count is never suppressed: 19 bookings is simply 19 bookings.
        assert kpis[MetricName.COMPLETED].value == 19

    def test_revenue_is_exact_to_the_fils(self):
        facts = [booking(starts_at=at(i % 28 + 1), price="0.10") for i in range(1000)]
        kpis = by_metric(m.booking_kpis(frame(facts)))
        assert kpis[MetricName.REVENUE].value == Decimal("100.00")
        assert kpis[MetricName.AVERAGE_TICKET].value == Decimal("0.10")

    def test_rows_in_another_currency_are_set_aside_and_counted(self):
        bookings, excluded = m.booking_frame(
            [booking(starts_at=at(1)), booking(starts_at=at(2), currency="USD")], currency="SAR"
        )
        assert len(bookings) == 1
        assert excluded == 1


class TestPaymentKpis:
    def test_collected_is_net_of_refunds_and_confined_to_the_window(self):
        completed = booking(starts_at=at(10))
        payments = m.payment_frame(
            [
                PaymentFact(
                    booking_id=completed.id,
                    status=PaymentStatus.PARTIALLY_REFUNDED,
                    amount_minor=15000,
                    refunded_minor=5000,
                    currency="SAR",
                    captured_at=at(9),
                    refunded_at=at(12),
                ),
                PaymentFact(
                    booking_id=uuid4(),
                    status=PaymentStatus.CAPTURED,
                    amount_minor=9900,
                    refunded_minor=0,
                    currency="SAR",
                    captured_at=at(15, month=7),
                    refunded_at=None,
                ),
            ],
            currency="SAR",
        )[0]
        kpis = by_metric(m.payment_kpis(payments, frame([completed]), AUGUST))
        assert kpis[MetricName.COLLECTED].value == Decimal("100.00")
        assert kpis[MetricName.REFUNDED].value == Decimal("50.00")

    def test_a_booking_prepaid_before_the_window_still_counts_as_prepaid(self):
        facts = [booking(starts_at=at(i + 1)) for i in range(20)]
        prepaid = [
            PaymentFact(
                booking_id=fact.id,
                status=PaymentStatus.CAPTURED,
                amount_minor=15000,
                refunded_minor=0,
                currency="SAR",
                captured_at=at(20, month=7),
                refunded_at=None,
            )
            for fact in facts[:5]
        ]
        payments = m.payment_frame(prepaid, currency="SAR")[0]
        kpis = by_metric(m.payment_kpis(payments, frame(facts), AUGUST))
        assert kpis[MetricName.PREPAID_SHARE].value == Decimal("0.2500")
        assert kpis[MetricName.COLLECTED].value == Decimal("0.00")


class TestCustomerKpis:
    def test_new_means_a_first_ever_visit_inside_the_window(self):
        newcomer, regular = uuid4(), uuid4()
        bookings = frame(
            [
                booking(starts_at=at(3), customer=newcomer),
                booking(starts_at=at(4), customer=regular),
            ]
        )
        visits = m.visit_frame(
            [
                visit(newcomer, first=at(3), last=at(3)),
                visit(regular, first=datetime(2025, 1, 5, tzinfo=UTC), last=at(4), upcoming=True),
            ]
        )
        kpis = by_metric(m.customer_kpis(bookings, visits, AUGUST))
        assert kpis[MetricName.NEW_CUSTOMERS].value == 1
        assert kpis[MetricName.RETURNING_CUSTOMERS].value == 1
        assert kpis[MetricName.REPEAT_RATE].suppressed

    def test_lapsed_leaves_out_the_rebooked_the_recent_and_the_long_gone(self):
        end = AUGUST.ends_at
        visits = m.visit_frame(
            [
                visit(uuid4(), first=end - timedelta(days=200), last=end - timedelta(days=90)),
                visit(
                    uuid4(),
                    first=end - timedelta(days=200),
                    last=end - timedelta(days=90),
                    upcoming=True,
                ),
                visit(uuid4(), first=end - timedelta(days=200), last=end - timedelta(days=30)),
                visit(uuid4(), first=end - timedelta(days=900), last=end - timedelta(days=400)),
            ]
        )
        kpis = by_metric(m.customer_kpis(frame([]), visits, AUGUST))
        assert kpis[MetricName.LAPSED_CUSTOMERS].value == 1


class TestUtilization:
    def test_scheduled_minutes_follow_the_week_and_its_exceptions(self):
        fact = ProviderCapacityFact(
            provider_id=PROVIDER,
            weekly=tuple(
                WorkingWindow(weekday=d, start_minute=540, end_minute=1020) for d in range(5)
            ),
            exceptions=(
                ScheduleException(on_date=date(2026, 8, 4)),  # Tuesday: closed
                ScheduleException(  # Saturday: opened 10:00-14:00
                    on_date=date(2026, 8, 8),
                    windows=(WorkingWindow(weekday=5, start_minute=600, end_minute=840),),
                ),
            ),
        )
        # Mon, Wed, Thu, Fri at 8 hours, plus Saturday's 4: 32 + 4 hours.
        assert m.scheduled_minutes(fact, FIRST_FULL_WEEK) == 36 * 60

    def test_cancelled_and_no_show_time_is_not_booked_time(self):
        fact = ProviderCapacityFact(
            provider_id=PROVIDER,
            weekly=(WorkingWindow(weekday=0, start_minute=540, end_minute=1020),),
            exceptions=(),
        )
        bookings = frame(
            [
                booking(starts_at=at(3, 10), minutes=120),
                booking(starts_at=at(3, 13), status=BookingStatus.CANCELLED),
                booking(starts_at=at(3, 15), status=BookingStatus.NO_SHOW),
            ]
        )
        utilization = m.utilization_frame(bookings, [fact], FIRST_FULL_WEEK)
        assert utilization.loc[0, "booked_minutes"] == 120
        assert m.utilization_kpi(utilization).value == Decimal("0.2500")


class TestPeriods:
    def test_a_late_evening_utc_booking_lands_on_the_next_local_day(self):
        # 22:30 UTC on 1 August is 01:30 on 2 August in Riyadh.
        instant = datetime(2026, 8, 1, 22, 30, tzinfo=UTC)
        starts = frame([booking(starts_at=instant)])["starts_at"]
        assert m.bucket(starts, timezone=RIYADH, granularity=Granularity.DAY).iloc[0] == date(
            2026, 8, 2
        )

    def test_weeks_start_on_monday(self):
        starts = frame([booking(starts_at=at(6))])["starts_at"]  # Thursday
        assert m.bucket(starts, timezone=RIYADH, granularity=Granularity.WEEK).iloc[0] == date(
            2026, 8, 3
        )

    def test_a_quiet_day_is_zero_rather_than_missing(self):
        table = m.outcome_series(frame([booking(starts_at=at(5))]), AUGUST, Granularity.DAY)
        assert len(table) == 31
        assert table.loc[date(2026, 8, 5), "completed"] == 1
        assert int(table.to_numpy().sum()) == 1

    def test_peak_hours_use_the_branch_timezone(self):
        dubai = uuid4()
        facts = [booking(starts_at=datetime(2026, 8, 3, 6, 0, tzinfo=UTC), location=dubai)]
        matrix = m.peak_hours_matrix(
            frame(facts), {str(dubai): "Asia/Dubai"}, default_timezone=RIYADH
        )
        assert matrix.loc[0, 10] == 1  # Monday, 10:00 in Dubai


class TestRetention:
    def test_cohorts_smaller_than_five_are_hidden(self):
        window = build_window(
            date_from=date(2026, 7, 1),
            date_to=date(2026, 8, 31),
            timezone=RIYADH,
            today=date(2026, 9, 14),
        )
        july = [uuid4() for _ in range(5)]
        august = [uuid4() for _ in range(2)]
        facts = [booking(starts_at=at(5, month=7), customer=c) for c in july]
        facts += [booking(starts_at=at(10), customer=c) for c in july[:3]]
        facts += [booking(starts_at=at(12), customer=c) for c in august]
        visits = [visit(c, first=at(5, month=7), last=at(10)) for c in july]
        visits += [visit(c, first=at(12), last=at(12)) for c in august]

        matrix = m.retention_matrix(frame(facts), m.visit_frame(visits), window)

        assert matrix.loc[date(2026, 7, 1), 0] == 1.0
        assert matrix.loc[date(2026, 7, 1), 1] == pytest.approx(0.6)
        assert math.isnan(matrix.loc[date(2026, 8, 1), 0])


class TestForecast:
    @staticmethod
    def weekly(values: list[int]) -> pd.Series:
        weeks = [date(2026, 3, 2) + timedelta(weeks=i) for i in range(len(values))]
        return pd.Series(values, index=weeks, dtype="int64")

    def test_refuses_fewer_than_eight_weeks(self):
        with pytest.raises(InsufficientDataError):
            m.linear_forecast(self.weekly([5] * 7), metric=ForecastMetric.BOOKINGS, horizon_weeks=4)

    def test_recovers_a_straight_line(self):
        history = self.weekly([10 + 2 * i for i in range(10)])
        forecast = m.linear_forecast(history, metric=ForecastMetric.BOOKINGS, horizon_weeks=2)

        assert forecast.slope_per_week == Decimal("2.0")
        future = [point for point in forecast.points if point.is_forecast]
        assert [point.value for point in future] == [Decimal("30.0"), Decimal("32.0")]
        # A perfect line leaves no residuals, so the band collapses onto it.
        assert future[0].lower == future[0].value == future[0].upper

    def test_the_current_partial_week_is_left_out(self):
        facts = [booking(starts_at=at(3)), booking(starts_at=at(10)), booking(starts_at=at(11))]
        history = m.weekly_history(
            frame(facts), metric=ForecastMetric.BOOKINGS, timezone=RIYADH, as_of=at(12)
        )
        assert list(history.index) == [date(2026, 8, 3)]
        assert history.iloc[0] == 1


class TestBreakdown:
    def test_ranked_by_completed_revenue_with_exact_shares(self):
        colour = uuid4()
        facts = [
            booking(starts_at=at(1), price="100.00"),
            booking(starts_at=at(2), price="300.00", service=colour),
            booking(
                starts_at=at(3), price="999.00", service=colour, status=BookingStatus.CANCELLED
            ),
        ]
        rows = m.breakdown(frame(facts), Dimension.SERVICE, {str(colour): ("Colour", "صبغة")})

        assert [row.label_en for row in rows] == ["Colour", str(SERVICE)]
        assert rows[0].revenue == Decimal("300.00")
        assert (rows[0].bookings, rows[0].completed) == (2, 1)
        assert rows[0].share_of_revenue == Decimal("0.7500")


class TestFinancialSummary:
    def test_the_ledger_adds_up_to_the_fils(self):
        tenant, business = uuid4(), uuid4()

        def line(*, reversal: bool) -> CommissionLine:
            return CommissionLine(
                id=uuid4(),
                tenant_id=tenant,
                business_id=business,
                booking_id=uuid4(),
                customer_id=uuid4(),
                source="marketplace",
                commission_class=CommissionClass.NEW_MARKETPLACE,
                base_amount=Money(amount=Decimal("150.00")),
                rate_pct=Decimal("35"),
                amount=Money(amount=Decimal("52.50")),
                is_reversal=reversal,
            )

        summary = m.financial_summary(
            bookings=frame([booking(starts_at=at(3), price="172.50")]),
            payments=m.payment_frame([], currency="SAR")[0],
            lines=[line(reversal=False), line(reversal=True)],
            invoices=[
                Invoice(
                    id=uuid4(),
                    tenant_id=tenant,
                    business_id=business,
                    period=BillingPeriod(
                        period_start=date(2026, 8, 1), period_end=date(2026, 9, 1)
                    ),
                    status=InvoiceStatus.OVERDUE,
                    subscription_amount=Decimal("199.00"),
                    commission_amount=Decimal("52.50"),
                    vat_amount=Decimal("37.73"),
                    total_amount=Decimal("289.23"),
                )
            ],
            payouts=[
                Payout(
                    id=uuid4(),
                    tenant_id=tenant,
                    business_id=business,
                    payout_date=date(2026, 8, 4),
                    collected_amount=Money(amount=Decimal("172.50")),
                    processing_fee=Money(amount=Decimal("4.31")),
                    commission_netted=Money(amount=Decimal("52.50")),
                )
            ],
            window=AUGUST,
            currency="SAR",
        )

        assert summary.revenue == Decimal("172.50")
        assert summary.commission_accrued == Decimal("52.50")
        assert summary.commission_reversed == Decimal("52.50")
        assert summary.payouts_net == Decimal("115.69")
        assert summary.invoiced_total == Decimal("289.23")
        assert (summary.outstanding_invoices, summary.outstanding_total) == (1, Decimal("289.23"))
