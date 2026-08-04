"""`graphspec trace` command: overlay real OTLP executions on a declared graph.

Prints DOT to stdout (pipeable straight into `dot`), followed by the cost
table as DOT line comments so the combined stream stays valid DOT input.
"""

from __future__ import annotations

import sys

from graphspec.parser import load
from graphspec.trace.inputs import TraceInputError, load_otlp


def run(path: str, otlp: str, session: str | None = None) -> int:
    graph = load(path)
    errors = [d for d in graph.parse_diagnostics if d.severity == "error"]
    if errors:
        for d in errors:
            print(d.format(), file=sys.stderr)
        return 1

    try:
        data = load_otlp(otlp)
    except TraceInputError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    from graphspec.trace.mapping import correlate, parse_otlp

    spans = parse_otlp(data)
    corr = correlate(graph, spans, session=session)

    from graphspec.trace.overlay import overlay_dot
    from graphspec.trace.cost import cost_table

    dot = overlay_dot(graph, corr)
    table = cost_table(graph, corr)

    sys.stdout.write(dot)
    for line in table.splitlines():
        print(f"// {line}")

    return 0
