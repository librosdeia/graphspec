"""E-NO-TERMINAL: every node has a path to some node listed in terminals."""
from graphspec.diagnostics import Diagnostic
from graphspec.model import Graph
from graphspec import analysis
from graphspec.rules import rule


@rule("E-NO-TERMINAL")
def e_no_terminal(graph: Graph) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    if not any(t in graph.nodes for t in graph.terminals):
        return diags

    reaching = analysis.nodes_reaching_terminals(graph)
    terminal_list = ", ".join(graph.terminals)

    for name, node in graph.nodes.items():
        if name not in reaching:
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "E-NO-TERMINAL",
                    "error",
                    f"node '{name}' has no path to any terminal",
                    f"connect it (directly or transitively) to one of: {terminal_list}; "
                    "on_timeout/on_exhausted targets count as edges",
                )
            )

    return diags
