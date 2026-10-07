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


#: name -> help text, for the labelled counters below.
_COUNTER_HELP = {
    "nova_ai_turns_total": "Assistant turns by agent and outcome (ok, handoff, degraded, busy).",
    "nova_ai_tool_calls_total": "Assistant tool calls by tool and outcome (ok, refused).",
    "nova_ai_injection_total": "Messages flagged as trying to instruct the model.",
}
_counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
_ai_turn_buckets: dict[str, list[int]] = {}
_ai_turn_sum: dict[str, float] = defaultdict(float)
_ai_turn_count: dict[str, int] = defaultdict(int)
#: A turn runs a model, so seconds to minutes rather than milliseconds.
AI_BUCKETS = (1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0, 300.0, 600.0)


def count(name: str, **labels: str) -> None:
    """Adds one to a labelled counter named in `_COUNTER_HELP`."""
    _counters[(name, tuple(sorted(labels.items())))] += 1


def record_ai_turn(*, agent: str, outcome: str, seconds: float) -> None:
    """One finished assistant turn: counted by outcome and timed by agent."""
    count("nova_ai_turns_total", agent=agent, outcome=outcome)
    counts = _ai_turn_buckets.setdefault(agent, [0] * len(AI_BUCKETS))
    for index, bound in enumerate(AI_BUCKETS):
        if seconds <= bound:
            counts[index] += 1
    _ai_turn_sum[agent] += seconds
    _ai_turn_count[agent] += 1


def reset() -> None:
    """For tests."""
    _counters.clear()
    _ai_turn_buckets.clear()
    _ai_turn_sum.clear()
    _ai_turn_count.clear()
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
    for name, help_text in _COUNTER_HELP.items():
        lines += [f"# HELP {name} {help_text}", f"# TYPE {name} counter"]
        for (counter, labels), amount in sorted(_counters.items()):
            if counter == name:
                pairs = ",".join(f'{k}="{_label(v)}"' for k, v in labels)
                lines.append(f"{name}{{{pairs}}} {amount}")
    lines += [
        "# HELP nova_ai_turn_duration_seconds Assistant turn latency by agent.",
        "# TYPE nova_ai_turn_duration_seconds histogram",
    ]
    for agent, counts in sorted(_ai_turn_buckets.items()):
        base = f'agent="{_label(agent)}"'
        for bound, bucket in zip(AI_BUCKETS, counts, strict=True):
            lines.append(f'nova_ai_turn_duration_seconds_bucket{{{base},le="{bound}"}} {bucket}')
        total = _ai_turn_count[agent]
        lines.append(f'nova_ai_turn_duration_seconds_bucket{{{base},le="+Inf"}} {total}')
        lines.append(f"nova_ai_turn_duration_seconds_sum{{{base}}} {_ai_turn_sum[agent]}")
        lines.append(f"nova_ai_turn_duration_seconds_count{{{base}}} {total}")
    for name, (help_text, value) in (extra_gauges or {}).items():
        lines += [f"# HELP {name} {help_text}", f"# TYPE {name} gauge", f"{name} {value}"]
    return "\n".join(lines) + "\n"
