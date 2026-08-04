"""E-READ-UNSET: every field a node reads is written by some upstream node or
edge on EVERY path that reaches it."""
from graphspec import analysis
from graphspec.diagnostics import Diagnostic
from graphspec.model import Graph
from graphspec.rules import rule


@rule("E-READ-UNSET")
def e_read_unset(graph: Graph) -> list[Diagnostic]:
    diags = []
    before = analysis.available_before(graph)
    reach = analysis.reachable(graph)
    for name, node in graph.nodes.items():
        if name not in reach:
            continue  # E-UNREACHABLE covers unreachable nodes
        for field, read in graph.reads_of(name):
            if read.optional:
                continue
            if field.name in before.get(name, set()):
                continue
            path = analysis.witness_unset_path(graph, name, field.name)
            witness = " → ".join(path)
            diags.append(
                Diagnostic(
                    graph.path,
                    field.line,
                    "E-READ-UNSET",
                    "error",
                    f"'{field.name}' is read by '{name}' but unset on path {witness}",
                    f"make a node or edge on that path write '{field.name}', "
                    f"or declare the read optional: '{name}?'",
                )
            )
    return diags
