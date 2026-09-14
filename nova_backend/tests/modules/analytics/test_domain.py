"""Report windows, names and the chart catalog. Pure — no database."""

from datetime import UTC, date, datetime

import pytest

from app.modules.analytics.domain import (
    CHARTS,
    CROSS_LOCATION_FEATURE,
    MAX_WINDOW_DAYS,
    METRIC_UNITS,
    ChartId,
    Granularity,
    MetricName,
    ReportWindow,
    build_window,
    parse_chart_id,
    resolve_granularity,
)
from app.modules.analytics.exceptions import ReportWindowError, UnknownChartError

RIYADH = "Asia/Riyadh"
TODAY = date(2026, 9, 14)


class TestReportWindow:
    def test_defaults_to_the_last_thirty_days_ending_today(self):
        window = build_window(date_from=None, date_to=None, timezone=RIYADH, today=TODAY)
        assert window.date_to == TODAY
        assert window.days == 30

    def test_both_ends_are_inclusive(self):
        window = build_window(
            date_from=date(2026, 8, 1), date_to=date(2026, 8, 31), timezone=RIYADH, today=TODAY
        )
        assert window.days == 31

    def test_a_local_day_starts_at_local_midnight(self):
        # ADR-0007: "August" in Riyadh begins at 21:00 UTC on 31 July.
        window = ReportWindow(
            date_from=date(2026, 8, 1), date_to=date(2026, 8, 31), timezone=RIYADH
        )
        assert window.starts_at == datetime(2026, 7, 31, 21, 0, tzinfo=UTC)
        assert window.ends_at == datetime(2026, 8, 31, 21, 0, tzinfo=UTC)

    def test_a_reversed_window_is_refused(self):
        with pytest.raises(ReportWindowError):
            build_window(
                date_from=date(2026, 8, 31), date_to=date(2026, 8, 1), timezone=RIYADH, today=TODAY
            )

    def test_an_unbounded_window_is_refused(self):
        with pytest.raises(ReportWindowError) as exc:
            build_window(
                date_from=date(2025, 1, 1), date_to=date(2026, 8, 31), timezone=RIYADH, today=TODAY
            )
        assert exc.value.status_code == 422
        assert str(MAX_WINDOW_DAYS) in exc.value.message


class TestGranularity:
    @pytest.mark.parametrize(
        ("days", "expected"),
        [
            (1, Granularity.DAY),
            (45, Granularity.DAY),
            (46, Granularity.WEEK),
            (180, Granularity.WEEK),
            (181, Granularity.MONTH),
        ],
    )
    def test_chosen_from_the_window_length(self, days, expected):
        start = date(2026, 1, 1)
        window = ReportWindow(
            date_from=start,
            date_to=start.fromordinal(start.toordinal() + days - 1),
            timezone=RIYADH,
        )
        assert resolve_granularity(window, None) is expected

    def test_an_explicit_granularity_wins(self):
        window = ReportWindow(
            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31), timezone=RIYADH
        )
        assert resolve_granularity(window, Granularity.DAY) is Granularity.DAY


class TestCatalog:
    def test_every_chart_is_defined_in_both_languages(self):
        assert set(CHARTS) == set(ChartId)
        for definition in CHARTS.values():
            assert definition.title_en and definition.title_ar
            assert definition.question_en and definition.question_ar

    def test_only_the_branch_comparison_is_plan_gated(self):
        gated = {chart_id for chart_id, d in CHARTS.items() if d.required_feature}
        assert gated == {ChartId.REVENUE_BY_LOCATION}
        assert CHARTS[ChartId.REVENUE_BY_LOCATION].required_feature == CROSS_LOCATION_FEATURE

    def test_every_metric_has_a_unit(self):
        assert set(METRIC_UNITS) == set(MetricName)

    def test_an_unknown_chart_is_a_404_not_a_500(self):
        with pytest.raises(UnknownChartError) as exc:
            parse_chart_id("revenue_by_horoscope")
        assert exc.value.status_code == 404
        assert parse_chart_id("peak_hours") is ChartId.PEAK_HOURS
