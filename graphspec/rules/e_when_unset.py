"""E-WHEN-UNSET: every identifier in a when is a state field written upstream."""
from graphspec.diagnostics import Diagnostic
from graphspec.expr import ExprError, identifiers
from graphspec.model import Graph
from graphspec.rules import rule
from graphspec import analysis


@rule("E-WHEN-UNSET")
def e_when_unset(graph: Graph) -> list[Diagnostic]:
    diags = []
    reachable = analysis.reachable(graph)
    available_after = analysis.available_after(graph)

    for edge in graph.edges:
        if not edge.when:
            continue
        try:
            idents = identifiers(edge.when)
        except ExprError as e:
            diags.append(Diagnostic(
                graph.path, edge.line, "E-PARSE", "error",
                f"when expression does not parse: {e}",
                "the grammar allows identifiers, quoted strings, numbers, true/false, "
                "== != < <= > >= && || ! and parentheses — nothing else",
            ))
            continue

        for ident in sorted(idents):
            if ident not in graph.state:
                diags.append(Diagnostic(
                    graph.path, edge.line, "E-WHEN-UNSET", "error",
                    f"identifier '{ident}' in when on edge '{edge.from_}' → '{edge.to}' "
                    f"is not a declared state field",
                    "declare the field under state: or fix the typo in the when expression",
                ))
                continue
            if edge.from_ not in graph.nodes or edge.from_ not in reachable:
                continue
            if ident not in available_after.get(edge.from_, set()):
                diags.append(Diagnostic(
                    graph.path, edge.line, "E-WHEN-UNSET", "error",
                    f"identifier '{ident}' in when on edge '{edge.from_}' → '{edge.to}' "
                    f"is not written upstream (writes by '{edge.from_}' itself count)",
                    "write the field on every path reaching this edge before it is tested",
                ))

    return diags
