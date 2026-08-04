"""Per-node cost table: a fixed-width text summary of a trace correlation.

Consumes :class:`graphspec.trace.mapping.Correlation` only — this module knows
nothing about spans or OTLP, and never emits its own DOT (that rule belongs to
the renderer, not here; this is plain text for the CLI's stdout).
"""

from __future__ import annotations

from graphspec.model import Graph
from graphspec.trace.mapping import Correlation

_HEADERS = ("node", "visits", "tokens", "latency")
_GAP = "  "


def _latency_str(ms: float) -> str:
    return f"{ms / 1000.0:.1f}s"


def cost_table(graph: Graph, corr: Correlation) -> str:
    """Render a fixed-width per-node cost table, followed by drift/unexecuted notes.

    Rows cover executed nodes only (those with at least one recorded visit),
    sorted by tokens descending, ties broken by name ascending. A TOTAL row
    follows. If any declared nodes never ran, a single "not executed: ..."
    line lists them. Drift entries — units that ran but were never declared —
    are each surfaced as a "drift: " line; drift is a feature, not a failure,
    so nothing here is phrased as an error.
    """
    nodes = sorted(corr.visits.keys(), key=lambda n: (-corr.tokens.get(n, 0), n))

    rows: list[tuple[str, int, int, str]] = []
    total_visits = 0
    total_tokens = 0
    total_latency_ms = 0.0
    for name in nodes:
        visits = corr.visits.get(name, 0)
        tokens = corr.tokens.get(name, 0)
        latency_ms = corr.latency_ms.get(name, 0.0)
        rows.append((name, visits, tokens, _latency_str(latency_ms)))
        total_visits += visits
        total_tokens += tokens
        total_latency_ms += latency_ms

    total_row = ("TOTAL", total_visits, total_tokens, _latency_str(total_latency_ms))
    all_rows = rows + [total_row]

    w_node = max(len(_HEADERS[0]), *(len(r[0]) for r in all_rows))
    w_visits = max(len(_HEADERS[1]), *(len(str(r[1])) for r in all_rows))
    w_tokens = max(len(_HEADERS[2]), *(len(str(r[2])) for r in all_rows))
    w_latency = max(len(_HEADERS[3]), *(len(r[3]) for r in all_rows))

    def fmt(name: str, visits: object, tokens: object, latency: str) -> str:
        return (
            f"{str(name):<{w_node}}{_GAP}"
            f"{str(visits):>{w_visits}}{_GAP}"
            f"{str(tokens):>{w_tokens}}{_GAP}"
            f"{latency:>{w_latency}}"
        )

    lines = [fmt(*_HEADERS)]
    lines.append("-" * len(lines[0]))
    for row in rows:
        lines.append(fmt(*row))
    lines.append(fmt(*total_row))

    if corr.unexecuted:
        lines.append("not executed: " + ", ".join(corr.unexecuted))

    for entry in corr.drift:
        lines.append(f"drift: {entry}")

    return "\n".join(lines) + "\n"
