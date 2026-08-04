"""E-CYCLE-CAP: every cycle contains at least one edge with max, counter (a number field) and on_exhausted."""
from graphspec import analysis
from graphspec.diagnostics import Diagnostic
from graphspec.model import Graph
from graphspec.rules import rule


@rule("E-CYCLE-CAP")
def e_cycle_cap(graph: Graph) -> list[Diagnostic]:
    diags = []

    cycle = analysis.uncapped_cycle(graph)
    if cycle is not None:
        pairs = list(zip(cycle, cycle[1:]))
        candidate_lines = [
            e.line for e in graph.edges
            if (e.from_, e.to) in pairs
        ]
        line = min(candidate_lines) if candidate_lines else 0
        diags.append(
            Diagnostic(
                graph.path,
                line,
                "E-CYCLE-CAP",
                "error",
                f"cycle <{' → '.join(cycle)}> has no capped edge",
                "give one edge of the cycle max: N, counter: <number field> and on_exhausted: <target>",
            )
        )

    for edge in graph.edges:
        if not edge.counter:
            continue
        field = graph.state.get(edge.counter)
        if field is None or field.type != "number":
            diags.append(
                Diagnostic(
                    graph.path,
                    edge.line,
                    "E-CYCLE-CAP",
                    "error",
                    f"counter '{edge.counter}' must be a declared number state field",
                    "declare it in state: {type: number} or fix the counter name",
                )
            )

    return diags
