"""E-TERMINAL: every terminals member has no outgoing edges; every kind: terminal node is listed in terminals."""
from graphspec.diagnostics import Diagnostic
from graphspec.model import Graph
from graphspec.rules import rule


@rule("E-TERMINAL")
def e_terminal(graph: Graph) -> list[Diagnostic]:
    diags = []

    for name in graph.terminals:
        node = graph.nodes.get(name)
        if node is None:
            continue
        if graph.out_edges(name):
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "E-TERMINAL",
                    "error",
                    f"terminal '{name}' has outgoing edges",
                    "a terminal ends the run; remove its outgoing edges or drop it from terminals",
                )
            )

    for name, node in graph.nodes.items():
        if node.kind == "terminal" and name not in graph.terminals:
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "E-TERMINAL",
                    "error",
                    f"node '{name}' has kind terminal but is not listed in terminals",
                    f"add '{name}' to terminals",
                )
            )

    return diags
