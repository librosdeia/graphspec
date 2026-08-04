"""Run the rule registry over a parsed graph and format the findings."""

from __future__ import annotations

from graphspec.diagnostics import Diagnostic, sort_diagnostics
from graphspec.model import Graph
from graphspec.parser import load
import graphspec.rules as rules_pkg


def run_rules(graph: Graph, target: str | None = None) -> list[Diagnostic]:
    """Parse diagnostics + every registered rule, in stable output order.

    When the parse failed structurally (no nodes), rules are skipped: the parse
    error is the actionable finding.
    """
    diags = list(graph.parse_diagnostics)
    if graph.nodes:
        for fn in rules_pkg.ALL_RULES.values():
            diags.extend(fn(graph))
        if target:
            from graphspec.rules.w_advisory import advisory_warnings
            diags.extend(advisory_warnings(graph, target))
    return sort_diagnostics(diags)


def run(path: str, strict: bool = False, target: str | None = None) -> int:
    """CLI entry: print findings, return exit code (1 on error, 0 otherwise;
    --strict promotes warnings to errors)."""
    graph = load(path)
    diags = run_rules(graph, target=target)
    for d in diags:
        print(d.format())
    errors = [d for d in diags if d.severity == "error" or (strict and d.severity == "warning")]
    if not diags:
        print(f"{path}: OK")
    return 1 if errors else 0
