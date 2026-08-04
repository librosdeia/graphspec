"""E-EDGE-ENDS: every edge from/to (including node-valued escape targets) names a declared node."""
from graphspec.diagnostics import Diagnostic
from graphspec.model import RESERVED_TARGETS, Graph
from graphspec.rules import rule


@rule("E-EDGE-ENDS")
def e_edge_ends(graph: Graph) -> list[Diagnostic]:
    diags = []

    for edge in graph.edges:
        if edge.from_ not in graph.nodes:
            diags.append(Diagnostic(
                graph.path, edge.line, "E-EDGE-ENDS", "error",
                f"edge 'from: {edge.from_}' names an undeclared node",
                f"declare '{edge.from_}' under nodes: or fix the typo",
            ))
        if edge.to not in graph.nodes:
            diags.append(Diagnostic(
                graph.path, edge.line, "E-EDGE-ENDS", "error",
                f"edge 'to: {edge.to}' names an undeclared node",
                f"declare '{edge.to}' under nodes: or fix the typo",
            ))
        if edge.on_exhausted and edge.on_exhausted not in RESERVED_TARGETS and edge.on_exhausted not in graph.nodes:
            diags.append(Diagnostic(
                graph.path, edge.line, "E-EDGE-ENDS", "error",
                f"edge 'on_exhausted: {edge.on_exhausted}' names an undeclared node",
                f"declare '{edge.on_exhausted}' under nodes: or fix the typo",
            ))

    for node in graph.nodes.values():
        target = node.on_timeout
        if target and target not in RESERVED_TARGETS and target not in graph.nodes:
            diags.append(Diagnostic(
                graph.path, node.line, "E-EDGE-ENDS", "error",
                f"node '{node.name}' has 'on_timeout: {target}' naming an undeclared node",
                f"declare '{target}' under nodes: or fix the typo",
            ))

    if not graph.entry or graph.entry not in graph.nodes:
        diags.append(Diagnostic(
            graph.path, 0, "E-EDGE-ENDS", "error",
            f"entry '{graph.entry}' names an undeclared node",
            f"declare '{graph.entry}' under nodes: or fix the typo",
        ))

    for terminal in graph.terminals:
        if terminal not in graph.nodes:
            diags.append(Diagnostic(
                graph.path, 0, "E-EDGE-ENDS", "error",
                f"terminal '{terminal}' names an undeclared node",
                f"declare '{terminal}' under nodes: or fix the typo",
            ))

    return diags
