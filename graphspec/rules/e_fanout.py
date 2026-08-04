"""E-FANOUT: fan_out_over names a list field, as is present, and the downstream join node declares join."""
from graphspec.diagnostics import Diagnostic
from graphspec.model import Graph
from graphspec.rules import rule


@rule("E-FANOUT")
def e_fanout(graph: Graph) -> list[Diagnostic]:
    diags = []
    for node in graph.nodes.values():
        if not node.fan_out_over:
            continue

        field = graph.state.get(node.fan_out_over)
        if field is None or field.type != "list":
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "E-FANOUT",
                    "error",
                    f"fan-out node '{node.name}' has fan_out_over "
                    f"'{node.fan_out_over}' which is not a declared list field",
                    "Declare a state field with type: list matching fan_out_over, or fix the name.",
                )
            )

        if not node.as_:
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "E-FANOUT",
                    "error",
                    f"'{node.name}' has fan_out_over but no 'as' — the per-item "
                    "binding is required",
                    "Add an 'as' name for the per-item binding.",
                )
            )

        for edge in graph.edges:
            if edge.from_ != node.name or edge.synthetic is not None:
                continue
            successor = graph.nodes.get(edge.to)
            if successor is None or successor.join:
                continue
            diags.append(
                Diagnostic(
                    graph.path,
                    edge.line,
                    "E-FANOUT",
                    "error",
                    f"downstream node '{successor.name}' of fan-out "
                    f"'{node.name}' declares no join policy",
                    "Add a join policy (all/any/majority/first) on the downstream node.",
                )
            )

        if graph.writes_of(node.name):
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "E-FANOUT",
                    "error",
                    f"fan-out node '{node.name}' declares state writes; in "
                    "graphspec 1 results flow through the join node",
                    "Remove state writes from the fan-out node; write results from the join node instead.",
                )
            )

    return diags
