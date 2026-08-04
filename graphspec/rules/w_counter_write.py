"""W-COUNTER-WRITE: a counter field is listed in a node's write: list."""

from graphspec.diagnostics import Diagnostic
from graphspec.model import Graph
from graphspec.rules import rule


@rule("W-COUNTER-WRITE")
def w_counter_write(graph: Graph) -> list[Diagnostic]:
    diags = []
    for name in graph.counter_fields():
        f = graph.state.get(name)
        if f is not None and f.write:
            diags.append(
                Diagnostic(
                    graph.path,
                    f.line,
                    "W-COUNTER-WRITE",
                    "warning",
                    f"counter '{f.name}' is written by edges; nodes must not list it in write:",
                    "remove the node from write: — the edge's counter: already increments it",
                )
            )
    return diags
