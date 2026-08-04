"""E-KIND: every node has a valid kind; every impl path exists on disk."""

import os

from graphspec.diagnostics import Diagnostic
from graphspec.model import KINDS, Graph
from graphspec.rules import rule


@rule("E-KIND")
def e_kind(graph: Graph) -> list[Diagnostic]:
    diags = []
    valid_kinds = ", ".join(sorted(KINDS))
    for node in graph.nodes.values():
        if node.kind not in KINDS:
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "E-KIND",
                    "error",
                    f"node '{node.name}' has invalid kind '{node.kind}'",
                    f"kind must be one of: {valid_kinds}",
                )
            )
        if node.impl:
            resolved = os.path.join(os.path.dirname(graph.path) or ".", node.impl)
            if not os.path.isfile(resolved):
                diags.append(
                    Diagnostic(
                        graph.path,
                        node.line,
                        "E-KIND",
                        "error",
                        f"impl path '{node.impl}' does not exist (resolved relative to the YAML file)",
                        "create the file next to the YAML or fix the path",
                    )
                )
    return diags
