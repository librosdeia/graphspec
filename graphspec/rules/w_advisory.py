"""W-ADVISORY: advisory-only fields for --target claude.

Not registered as a rule — it is invoked directly by validate.py only when a
--target is passed, since it is target-specific rather than a graph-shape check.
"""

from graphspec.diagnostics import Diagnostic
from graphspec.model import Graph

_HINT = "see docs/FORMAT.md enforced-vs-advisory table"


def advisory_warnings(graph: Graph, target: str) -> list[Diagnostic]:
    if target != "claude":
        return []

    diags = []
    for node in graph.nodes.values():
        if node.budget_tokens is not None:
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "W-ADVISORY",
                    "warning",
                    f"'{node.name}' declares budget_tokens, advisory for --target claude — "
                    "documented in the generated contract, not enforced by generated code",
                    _HINT,
                )
            )
        if node.kind == "human" and (node.timeout is not None or node.on_timeout is not None):
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "W-ADVISORY",
                    "warning",
                    f"'{node.name}' declares timeout/on_timeout, advisory for --target claude — "
                    "documented in the generated contract, not enforced by generated code",
                    _HINT,
                )
            )

    if graph.checkpoints_after:
        diags.append(
            Diagnostic(
                graph.path,
                0,
                "W-ADVISORY",
                "warning",
                "checkpoints are advisory for --target claude",
                _HINT,
            )
        )

    return diags
