"""E-UNREACHABLE: every node is reachable from entry."""
from graphspec.diagnostics import Diagnostic
from graphspec.model import Graph
from graphspec import analysis
from graphspec.rules import rule


@rule("E-UNREACHABLE")
def e_unreachable(graph: Graph) -> list[Diagnostic]:
    diags = []
    if graph.entry not in graph.nodes:
        return diags
    reachable = analysis.reachable(graph)
    for name, node in graph.nodes.items():
        if name not in reachable:
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "E-UNREACHABLE",
                    "error",
                    f"node '{name}' is not reachable from entry '{graph.entry}'",
                    "add an edge from a reachable node or remove it; on_timeout/on_exhausted targets count as edges",
                )
            )
    return diags
