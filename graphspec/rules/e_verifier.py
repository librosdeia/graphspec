"""E-VERIFIER: a node with verifies: X differs from X in agent or in model."""
from graphspec.diagnostics import Diagnostic
from graphspec.model import Graph
from graphspec.rules import rule


@rule("E-VERIFIER")
def e_verifier(graph: Graph) -> list[Diagnostic]:
    diags = []
    for node in graph.nodes.values():
        target_name = node.verifies
        if not target_name:
            continue
        target = graph.nodes.get(target_name)
        if target is None:
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "E-VERIFIER",
                    "error",
                    f"verifies target '{target_name}' is not a declared node",
                    "point verifies at a node declared in this graph.",
                )
            )
            continue
        if node.agent == target.agent and node.model == target.model:
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "E-VERIFIER",
                    "error",
                    f"'{node.name}' verifies '{target_name}' but shares its agent and model — "
                    "a verifier must differ in at least one",
                    "give the verifier a different agent or a different model; "
                    "self-review misses what the author missed",
                )
            )
    return diags
