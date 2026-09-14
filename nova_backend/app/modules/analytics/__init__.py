"""Bounded context: ANALYTICS — a business's own numbers, and the charts that show them.

Aggregates      none — this context owns no tables
Depends on      booking, payment, queue, billing, catalog (their SERVICES only)
Status          implemented
Plan            docs/13-Business-Agents-and-Analytics.md, ADR-0011

Analytics answers questions that span five contexts and owns none of their
data. It reads narrow fact projections that each owner exposes on its service
(`BookingService.list_booking_facts`, `PaymentService.list_payment_facts`, ...)
and never another module's tables. A report asked a narrow question, so it gets
a narrow answer, with nothing about a customer beyond an opaque id.

Layers:
    domain.py    windows, metric and chart names, sample thresholds   (pure)
    metrics.py   pandas + numpy over fact frames                       (pure)
    charts.py    Plotly figure JSON with bilingual labels              (pure)
    service.py   loads facts through services, memoised per request

numpy, pandas and plotly are imported by `metrics.py` and `charts.py` and
nowhere else; `tests/test_architecture.py` enforces it.

Money is summed as int64 fils and leaves as Decimal. Floats exist only inside
chart figures, which are presentation (docs/06 section 8).

Public surface — what other modules may import:
    from app.modules.analytics.service import AnalyticsService
    from app.modules.analytics.domain import (
        ChartId, Dimension, ForecastMetric, Granularity, MetricName, ReportWindow,
    )
    from app.modules.analytics.schemas import ChartOut

Internal — do not import from other modules:
    metrics.py, charts.py, dependencies.py, router.py
"""
