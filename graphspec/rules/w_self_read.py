"""W-SELF-READ: a node reads a state field that it also writes itself."""

from graphspec.diagnostics import Diagnostic
from graphspec.model import Graph
from graphspec.rules import rule


@rule("W-SELF-READ")
def w_self_read(graph: Graph) -> list[Diagnostic]:
    diags = []
    for f in graph.state.values():
        for r in f.read:
            if r.node in f.write:
                diags.append(
                    Diagnostic(
                        graph.path,
                        f.line,
                        "W-SELF-READ",
                        "warning",
                        f"'{r.node}' reads '{f.name}' which it writes itself — "
                        "a self-read is redundant or a sign of confused data flow",
                        "drop the self-read or split the field if a prior value is truly needed",
                    )
                )
    return diags
