"""E-HUMAN: every kind: human node has timeout and on_timeout."""
from graphspec.diagnostics import Diagnostic
from graphspec.model import Graph
from graphspec.rules import rule

_HINT = (
    "humans go on holiday; declare how long to wait (e.g. 48h) and what "
    "happens then (escalate, fail, or a node)"
)


@rule("E-HUMAN")
def e_human(graph: Graph) -> list[Diagnostic]:
    diags = []
    for node in graph.nodes.values():
        if node.kind != "human":
            continue
        if not node.timeout:
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "E-HUMAN",
                    "error",
                    f"'{node.name}' is a human node without a timeout",
                    _HINT,
                )
            )
        if not node.on_timeout:
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "E-HUMAN",
                    "error",
                    f"'{node.name}' is a human node without on_timeout",
                    _HINT,
                )
            )
    return diags
