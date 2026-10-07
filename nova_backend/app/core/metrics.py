"""Process-local Prometheus metrics, rendered as text.

Deliberately dependency-free: the exposition format is a few lines of text, and
a client library would mean a new lock-file entry for what is, today, one
counter and one histogram. Each process keeps its own numbers, so the API's
`/metrics` describes the API; the outbox gauges are read from the database at
scrape time and so describe the whole system whichever process answers.
"""

from collections import defaultdict

#: Upper bounds in seconds. The API's target is p95 under 200 ms.
BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.5, 5.0, 10.0)

_requests: dict[tuple[str, str, str], int] = defaultdict(int)
_duration_buckets: dict[tuple[str, str], list[int]] = {}
_duration_sum: dict[tuple[str, str], float] = defaultdict(float)
_duration_count: dict[tuple[str, str], int] = defaultdict(int)


def record_request(*, method: str, route: str, status: int, seconds: float) -> None:
    """Counts one finished request. `route` is the path template, never the raw
    path, or every UUID would mint a new series."""
    _requests[(method, route, f"{status // 100}xx")] += 1
    key = (method, route)
    counts = _duration_buckets.setdefault(key, [0] * len(BUCKETS))
    for index, bound in enumerate(BUCKETS):
        if seconds <= bound:
            counts[index] += 1
    _duration_sum[key] += seconds
    _duration_count[key] += 1


def reset() -> None:
    """For tests."""
    _requests.clear()
    _duration_buckets.clear()
    _duration_sum.clear()
    _duration_count.clear()


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render(extra_gauges: dict[str, tuple[str, float]] | None = None) -> str:
    """The text exposition format. `extra_gauges` maps name -> (help, value)."""
    lines = [
        "# HELP nova_http_requests_total Finished HTTP requests.",
        "# TYPE nova_http_requests_total counter",
    ]
    for (method, route, status), count in sorted(_requests.items()):
        lines.append(
            f'nova_http_requests_total{{method="{_label(method)}",route="{_label(route)}",'
            f'status="{status}"}} {count}'
        )
    lines += [
        "# HELP nova_http_request_duration_seconds HTTP request latency.",
        "# TYPE nova_http_request_duration_seconds histogram",
    ]
    for (method, route), counts in sorted(_duration_buckets.items()):
        base = f'method="{_label(method)}",route="{_label(route)}"'
        for bound, count in zip(BUCKETS, counts, strict=True):
            lines.append(
                f'nova_http_request_duration_seconds_bucket{{{base},le="{bound}"}} {count}'
            )
        total = _duration_count[(method, route)]
        lines.append(f'nova_http_request_duration_seconds_bucket{{{base},le="+Inf"}} {total}')
        lines.append(
            f"nova_http_request_duration_seconds_sum{{{base}}} {_duration_sum[(method, route)]}"
        )
        lines.append(f"nova_http_request_duration_seconds_count{{{base}}} {total}")
    for name, (help_text, value) in (extra_gauges or {}).items():
        lines += [f"# HELP {name} {help_text}", f"# TYPE {name} gauge", f"{name} {value}"]
    return "\n".join(lines) + "\n"
