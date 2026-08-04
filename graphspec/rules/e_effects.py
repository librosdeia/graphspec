"""E-EFFECTS: every node with effects: external has an idempotency_key whose
template references only declared fields and the node's own as binding."""

import re

from graphspec.diagnostics import Diagnostic
from graphspec.model import EFFECTS, Graph
from graphspec.rules import rule

_REF_RE = re.compile(r"\{([^{}]+)\}")


@rule("E-EFFECTS")
def e_effects(graph: Graph) -> list[Diagnostic]:
    diags = []
    valid_effects = ", ".join(sorted(EFFECTS))
    for node in graph.nodes.values():
        if node.effects not in EFFECTS:
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "E-EFFECTS",
                    "error",
                    f"node '{node.name}' has invalid effects '{node.effects}'",
                    f"effects must be one of: {valid_effects}",
                )
            )
            continue

        if node.effects == "external" and not node.idempotency_key:
            diags.append(
                Diagnostic(
                    graph.path,
                    node.line,
                    "E-EFFECTS",
                    "error",
                    f"'{node.name}' has effects: external but no idempotency_key",
                    "an external effect must be safely re-runnable; key it on the state that identifies the work",
                )
            )

        if node.idempotency_key:
            allowed = set(graph.state)
            if node.as_:
                allowed.add(node.as_)
            for ref in _REF_RE.findall(node.idempotency_key):
                if ref not in allowed:
                    diags.append(
                        Diagnostic(
                            graph.path,
                            node.line,
                            "E-EFFECTS",
                            "error",
                            f"idempotency_key references '{{{ref}}}' which is neither a declared state field nor this node's 'as' binding",
                            "reference only declared state fields or this node's own 'as' binding",
                        )
                    )
    return diags
