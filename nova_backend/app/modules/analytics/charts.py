"""analytics · PRESENTATION — Plotly figures as JSON.

Layer rule: pure. Frames from `metrics.py` in, `ChartSpec` out. plotly is
imported here and nowhere else in the codebase.

A figure is Plotly's own JSON (`data` plus `layout`), serialised through
`plotly.io.to_json` so numpy values and NaN come out as plain numbers and nulls,
then parsed back into a dict so it nests inside an API response. The client
draws it with plotly.js (docs/13 section 7.1).

Every label follows the locale, and every name of a service, provider or branch
comes from its `name_en`/`name_ar` pair (ADR-0004). No figure carries a customer
id, name or phone number: aggregates only.
"""

import json
from collections.abc import Sequence
from datetime import date
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from app.modules.analytics.domain import (
    CHARTS,
    SOURCE_LABELS,
    TOP_N,
    BreakdownRow,
    ChartId,
    ChartSpec,
    Forecast,
)
from app.modules.analytics.metrics import OUTCOMES

#: One fixed categorical palette, legible on light and dark dashboards alike.
PALETTE = ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d"]

_OUTCOME_COLORS = {
    "completed": "#16a34a",
    "cancelled": "#9ca3af",
    "no_show": "#dc2626",
    "upcoming": "#2563eb",
}

_TEXT: dict[str, tuple[str, str]] = {
    "completed": ("Completed", "مكتملة"),
    "cancelled": ("Cancelled", "ملغاة"),
    "no_show": ("No-show", "لم يحضر"),
    "upcoming": ("Upcoming", "قادمة"),
    "bookings": ("Bookings", "الحجوزات"),
    "revenue": ("Revenue", "الإيرادات"),
    "average_ticket": ("Average ticket", "متوسط قيمة الحجز"),
    "new": ("New", "جدد"),
    "returning": ("Returning", "عائدون"),
    "customers": ("Customers", "العملاء"),
    "utilization": ("Utilization (%)", "نسبة الإشغال (%)"),
    "booked_hours": ("Booked hours", "الساعات المحجوزة"),
    "scheduled_hours": ("Scheduled hours", "الساعات المجدولة"),
    "walk_ins": ("Walk-ins", "الحضور المباشر"),
    "average_wait": ("Average wait (minutes)", "متوسط الانتظار (دقائق)"),
    "net": ("Net payout", "صافي الدفعة"),
    "commission_netted": ("Commission deducted", "العمولة المخصومة"),
    "processing_fee": ("Processing fee", "رسوم المعالجة"),
    "subscription": ("Subscription", "الاشتراك"),
    "commission": ("Commission", "العمولة"),
    "processing": ("Processing", "المعالجة"),
    "vat": ("VAT", "ضريبة القيمة المضافة"),
    "weekly_bookings": ("Weekly bookings", "الحجوزات الأسبوعية"),
    "trend": ("Linear trend", "الاتجاه الخطي"),
    "band": ("95% band", "نطاق 95%"),
    "cohort": ("First-visit month", "شهر الزيارة الأولى"),
    "months_since": ("Months since first visit", "الأشهر منذ الزيارة الأولى"),
    "active_share": ("Returned (%)", "عادوا (%)"),
    "hour": ("Hour", "الساعة"),
    "new_marketplace": ("New marketplace client", "عميل جديد من السوق"),
    "repeat": ("Repeat", "متكرر"),
    "direct": ("Direct", "مباشر"),
    "exempt": ("Exempt or reversed", "معفى أو مسترد"),
}

_WEEKDAYS = (
    ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"),
)


def _t(key: str, locale: str) -> str:
    english, arabic = _TEXT[key]
    return arabic if locale == "ar" else english


def _label(pair: tuple[str, str], locale: str) -> str:
    return pair[1] if locale == "ar" else pair[0]


def _dates(values: Sequence[date]) -> list[str]:
    return [value.isoformat() for value in values]


def _major(minor: pd.Series) -> list[float]:
    """Fils to currency units, for drawing only. KPIs never come from here."""
    return (minor.astype(float) / 100).round(2).tolist()


def _layout(locale: str, **extra: Any) -> dict[str, Any]:
    layout: dict[str, Any] = {
        # No embedded Plotly theme: it is about 7 KB per figure, and the
        # dashboard applies its own. Transparent, so that theme shows through.
        "template": "none",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "colorway": PALETTE,
        "font": {"family": "Inter, 'Noto Sans Arabic', 'Segoe UI', Tahoma, sans-serif"},
        "margin": {"l": 56, "r": 24, "t": 16, "b": 56},
        "legend": {"orientation": "h", "y": -0.2},
        "hovermode": "x unified",
    }
    if locale == "ar":
        layout["legend"]["traceorder"] = "reversed"
    layout.update(extra)
    return layout


def _spec(chart_id: ChartId, figure: go.Figure, *, locale: str, data_points: int) -> ChartSpec:
    definition = CHARTS[chart_id]
    return ChartSpec(
        chart_id=chart_id,
        kind=definition.kind,
        title=definition.title(locale),
        description=definition.question(locale),
        locale=locale,
        figure=json.loads(pio.to_json(figure, validate=True)),
        data_points=data_points,
    )


# --- bookings ---------------------------------------------------------------


def bookings_trend(table: pd.DataFrame, *, locale: str) -> ChartSpec:
    figure = go.Figure()
    for outcome in OUTCOMES:
        figure.add_bar(
            name=_t(outcome, locale),
            x=_dates(table.index),
            y=table[outcome].tolist(),
            marker_color=_OUTCOME_COLORS[outcome],
        )
    figure.update_layout(
        _layout(locale, barmode="stack", yaxis={"title": {"text": _t("bookings", locale)}})
    )
    return _spec(ChartId.BOOKINGS_TREND, figure, locale=locale, data_points=len(table))


def booking_outcomes(table: pd.DataFrame, *, locale: str) -> ChartSpec:
    resolved = [outcome for outcome in OUTCOMES if outcome != "upcoming"]
    totals = [int(table[outcome].sum()) for outcome in resolved]
    figure = go.Figure(
        go.Pie(
            labels=[_t(outcome, locale) for outcome in resolved],
            values=totals,
            hole=0.55,
            sort=False,
            marker={"colors": [_OUTCOME_COLORS[outcome] for outcome in resolved]},
        )
    )
    figure.update_layout(_layout(locale, hovermode="closest"))
    return _spec(ChartId.BOOKING_OUTCOMES, figure, locale=locale, data_points=sum(totals))


def revenue_trend(series: pd.DataFrame, *, locale: str, currency: str) -> ChartSpec:
    completed = series["completed"].where(series["completed"] > 0)
    average = (series["revenue_minor"] / completed / 100).round(2)
    figure = go.Figure()
    figure.add_bar(
        name=f"{_t('revenue', locale)} ({currency})",
        x=_dates(series.index),
        y=_major(series["revenue_minor"]),
    )
    figure.add_scatter(
        name=f"{_t('average_ticket', locale)} ({currency})",
        x=_dates(series.index),
        y=average.tolist(),
        mode="lines+markers",
        yaxis="y2",
    )
    figure.update_layout(
        _layout(
            locale,
            yaxis={"title": {"text": f"{_t('revenue', locale)} ({currency})"}},
            yaxis2={"overlaying": "y", "side": "right", "showgrid": False},
        )
    )
    return _spec(ChartId.REVENUE_TREND, figure, locale=locale, data_points=len(series))


def _ranked_bar(
    chart_id: ChartId, rows: Sequence[BreakdownRow], *, locale: str, currency: str
) -> ChartSpec:
    top = list(rows)[:TOP_N][::-1]  # reversed, so the largest bar sits on top
    figure = go.Figure(
        go.Bar(
            orientation="h",
            x=[float(row.revenue) for row in top],
            y=[_label((row.label_en, row.label_ar), locale) for row in top],
            customdata=[[row.completed, row.bookings] for row in top],
            hovertemplate=(
                f"%{{y}}: %{{x:,.2f}} {currency}<br>"
                f"{_t('completed', locale)}: %{{customdata[0]}}<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        _layout(
            locale,
            hovermode="closest",
            xaxis={"title": {"text": f"{_t('revenue', locale)} ({currency})"}},
        )
    )
    return _spec(chart_id, figure, locale=locale, data_points=len(top))


def revenue_by_service(rows: Sequence[BreakdownRow], *, locale: str, currency: str) -> ChartSpec:
    return _ranked_bar(ChartId.REVENUE_BY_SERVICE, rows, locale=locale, currency=currency)


def revenue_by_provider(rows: Sequence[BreakdownRow], *, locale: str, currency: str) -> ChartSpec:
    return _ranked_bar(ChartId.REVENUE_BY_PROVIDER, rows, locale=locale, currency=currency)


def revenue_by_location(rows: Sequence[BreakdownRow], *, locale: str, currency: str) -> ChartSpec:
    return _ranked_bar(ChartId.REVENUE_BY_LOCATION, rows, locale=locale, currency=currency)


def source_mix(rows: Sequence[BreakdownRow], *, locale: str) -> ChartSpec:
    figure = go.Figure(
        go.Pie(
            labels=[_label(SOURCE_LABELS.get(row.key, (row.key, row.key)), locale) for row in rows],
            values=[row.bookings for row in rows],
            hole=0.55,
            sort=False,
        )
    )
    figure.update_layout(_layout(locale, hovermode="closest"))
    return _spec(
        ChartId.SOURCE_MIX, figure, locale=locale, data_points=sum(r.bookings for r in rows)
    )


# --- customers --------------------------------------------------------------


def new_vs_returning(table: pd.DataFrame, *, locale: str) -> ChartSpec:
    figure = go.Figure()
    for kind in ("new", "returning"):
        figure.add_bar(name=_t(kind, locale), x=_dates(table.index), y=table[kind].tolist())
    figure.update_layout(
        _layout(locale, barmode="stack", yaxis={"title": {"text": _t("customers", locale)}})
    )
    return _spec(ChartId.NEW_VS_RETURNING, figure, locale=locale, data_points=len(table))


def retention_cohorts(matrix: pd.DataFrame, *, locale: str) -> ChartSpec:
    z = (matrix.astype(float) * 100).round(1)
    figure = go.Figure(
        go.Heatmap(
            z=z.to_numpy().tolist(),
            x=[str(column) for column in matrix.columns],
            y=_dates(matrix.index),
            colorscale="Blues",
            zmin=0,
            zmax=100,
            colorbar={"title": {"text": _t("active_share", locale)}},
            hoverongaps=False,
        )
    )
    figure.update_layout(
        _layout(
            locale,
            hovermode="closest",
            xaxis={"title": {"text": _t("months_since", locale)}},
            yaxis={"title": {"text": _t("cohort", locale)}},
        )
    )
    return _spec(ChartId.RETENTION_COHORTS, figure, locale=locale, data_points=len(matrix))


# --- operations -------------------------------------------------------------


def peak_hours(matrix: pd.DataFrame, *, locale: str) -> ChartSpec:
    weekdays = _WEEKDAYS[1] if locale == "ar" else _WEEKDAYS[0]
    figure = go.Figure(
        go.Heatmap(
            z=matrix.to_numpy().tolist(),
            x=[f"{hour:02d}:00" for hour in matrix.columns],
            y=list(weekdays),
            colorscale="Blues",
            colorbar={"title": {"text": _t("bookings", locale)}},
        )
    )
    figure.update_layout(
        _layout(
            locale,
            hovermode="closest",
            xaxis={"title": {"text": _t("hour", locale)}},
            yaxis={"autorange": "reversed"},
        )
    )
    return _spec(
        ChartId.PEAK_HOURS, figure, locale=locale, data_points=int(matrix.to_numpy().sum())
    )


def provider_utilization(
    frame: pd.DataFrame, labels: dict[str, tuple[str, str]], *, locale: str
) -> ChartSpec:
    names = [
        _label(labels.get(provider_id, (provider_id, provider_id)), locale)
        for provider_id in frame["provider_id"]
    ]
    figure = go.Figure(
        go.Bar(
            x=names,
            y=(frame["utilization"] * 100).round(1).tolist(),
            customdata=list(
                zip(
                    (frame["booked_minutes"] / 60).round(1).tolist(),
                    (frame["scheduled_minutes"] / 60).round(1).tolist(),
                    strict=True,
                )
            ),
            hovertemplate=(
                f"%{{x}}: %{{y}}%<br>{_t('booked_hours', locale)}: %{{customdata[0]}}"
                f"<br>{_t('scheduled_hours', locale)}: %{{customdata[1]}}<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        _layout(locale, hovermode="closest", yaxis={"title": {"text": _t("utilization", locale)}})
    )
    return _spec(ChartId.PROVIDER_UTILIZATION, figure, locale=locale, data_points=len(frame))


def bookings_forecast(forecast: Forecast, *, locale: str) -> ChartSpec:
    history = [point for point in forecast.points if not point.is_forecast]
    future = [point for point in forecast.points if point.is_forecast]
    figure = go.Figure()
    figure.add_scatter(
        name=_t("weekly_bookings", locale),
        x=[point.week_start.isoformat() for point in history],
        y=[float(point.value) for point in history],
        mode="lines+markers",
    )
    if future:
        weeks = [point.week_start.isoformat() for point in future]
        figure.add_scatter(
            name=_t("band", locale),
            x=weeks + weeks[::-1],
            y=[float(point.upper or 0) for point in future]
            + [float(point.lower or 0) for point in future][::-1],
            fill="toself",
            fillcolor="rgba(37,99,235,0.15)",
            line={"width": 0},
            hoverinfo="skip",
        )
        figure.add_scatter(
            name=_t("trend", locale),
            x=[history[-1].week_start.isoformat(), *weeks],
            y=[float(history[-1].value)] + [float(point.value) for point in future],
            mode="lines",
            line={"dash": "dash"},
        )
    figure.update_layout(
        _layout(locale, yaxis={"title": {"text": _t("bookings", locale)}, "rangemode": "tozero"})
    )
    return _spec(ChartId.BOOKINGS_FORECAST, figure, locale=locale, data_points=len(forecast.points))


def queue_wait_times(series: pd.DataFrame, *, locale: str) -> ChartSpec:
    figure = go.Figure()
    figure.add_bar(
        name=_t("walk_ins", locale), x=_dates(series.index), y=series["walk_ins"].tolist()
    )
    figure.add_scatter(
        name=_t("average_wait", locale),
        x=_dates(series.index),
        y=series["average_wait_minutes"].round(1).tolist(),
        mode="lines+markers",
        yaxis="y2",
    )
    figure.update_layout(
        _layout(
            locale,
            yaxis={"title": {"text": _t("walk_ins", locale)}},
            yaxis2={
                "overlaying": "y",
                "side": "right",
                "showgrid": False,
                "title": {"text": _t("average_wait", locale)},
            },
        )
    )
    return _spec(ChartId.QUEUE_WAIT_TIMES, figure, locale=locale, data_points=len(series))


# --- the ledger ---------------------------------------------------------------


def payouts_breakdown(frame: pd.DataFrame, *, locale: str, currency: str) -> ChartSpec:
    figure = go.Figure()
    for column, key in (
        ("net_minor", "net"),
        ("commission_minor", "commission_netted"),
        ("processing_minor", "processing_fee"),
    ):
        figure.add_bar(
            name=_t(key, locale),
            x=_dates(frame.index),
            y=_major(frame[column]) if column in frame else [],
        )
    figure.update_layout(_layout(locale, barmode="stack", yaxis={"title": {"text": currency}}))
    return _spec(ChartId.PAYOUTS_BREAKDOWN, figure, locale=locale, data_points=len(frame))


def nova_charges(frame: pd.DataFrame, *, locale: str, currency: str) -> ChartSpec:
    figure = go.Figure()
    for column, key in (
        ("subscription_minor", "subscription"),
        ("commission_minor", "commission"),
        ("processing_minor", "processing"),
        ("vat_minor", "vat"),
    ):
        figure.add_bar(
            name=_t(key, locale),
            x=_dates(frame["period_start"]),
            y=_major(frame[column]),
        )
    figure.update_layout(
        # `relative` stacks a negative commission (a month of refunds) below zero.
        _layout(locale, barmode="relative", yaxis={"title": {"text": currency}})
    )
    return _spec(ChartId.NOVA_CHARGES, figure, locale=locale, data_points=len(frame))


def commission_by_class(frame: pd.DataFrame, *, locale: str, currency: str) -> ChartSpec:
    figure = go.Figure(
        go.Bar(
            x=[_t(str(name), locale) if str(name) in _TEXT else str(name) for name in frame.index],
            y=_major(frame["signed_minor"]) if "signed_minor" in frame else [],
        )
    )
    figure.update_layout(_layout(locale, hovermode="closest", yaxis={"title": {"text": currency}}))
    return _spec(ChartId.COMMISSION_BY_CLASS, figure, locale=locale, data_points=len(frame))


__all__ = [
    "PALETTE",
    "booking_outcomes",
    "bookings_forecast",
    "bookings_trend",
    "commission_by_class",
    "new_vs_returning",
    "nova_charges",
    "payouts_breakdown",
    "peak_hours",
    "provider_utilization",
    "queue_wait_times",
    "retention_cohorts",
    "revenue_by_location",
    "revenue_by_provider",
    "revenue_by_service",
    "revenue_trend",
    "source_mix",
]
