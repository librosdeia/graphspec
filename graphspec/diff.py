"""Semantic diff of two graph files: `graphspec diff OLD NEW [--format text|markdown]`.

A structural comparison of two parsed :class:`~graphspec.model.Graph` objects —
no new concepts. Node/edge/state additions, removals and attribute changes are
reported; file position (``.line``, ``.synthetic``) is never a semantic change
and is ignored throughout.
"""

from __future__ import annotations

import itertools
import sys
from dataclasses import dataclass, field

from graphspec.model import Edge, Graph, StateField
from graphspec.parser import load

# Order mirrors the attribute list in the unit's brief; it drives the order
# `details` lines are reported in for a single changed node/edge/state field.
NODE_ATTRS = [
    "kind", "agent", "model", "substrate", "effects", "idempotency_key",
    "fan_out_over", "as_", "concurrency", "isolation", "verifies", "join",
    "timeout", "on_timeout", "presents", "impl", "budget_tokens", "tools",
]
EDGE_ATTRS = ["when", "max", "counter", "on_exhausted"]
STATE_ATTRS = ["type", "values", "write"]

_KIND_TITLE = {"node": "Nodes", "edge": "Edges", "state": "State"}


@dataclass
class Change:
    kind: str  # "node" | "edge" | "state"
    action: str  # "added" | "removed" | "changed"
    key: str  # node name | "a → b" for edges | state field name
    details: list[str] = field(default_factory=list)


def _fmt(value) -> str:
    """Deterministic, human-readable rendering of an attribute value."""
    if value is None:
        return "none"
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, list):
        return "[" + ", ".join(_fmt(v) for v in value) + "]"
    return str(value)


def _fmt_reads(reads: frozenset[tuple[str, bool]]) -> str:
    items = sorted(f"{node}?" if optional else node for node, optional in reads)
    return "[" + ", ".join(f"'{i}'" for i in items) + "]"


def _attr_details(old_obj, new_obj, attrs: list[str]) -> list[str]:
    details = []
    for attr in attrs:
        ov, nv = getattr(old_obj, attr), getattr(new_obj, attr)
        if ov != nv:
            details.append(f"{attr}: {_fmt(ov)} → {_fmt(nv)}")
    return details


def _compare_nodes(old: Graph, new: Graph) -> list[Change]:
    old_names, new_names = set(old.nodes), set(new.nodes)
    changes = [Change("node", "added", name) for name in sorted(new_names - old_names)]
    changes += [Change("node", "removed", name) for name in sorted(old_names - new_names)]
    for name in sorted(old_names & new_names):
        details = _attr_details(old.nodes[name], new.nodes[name], NODE_ATTRS)
        if details:
            changes.append(Change("node", "changed", name, details))
    return changes


def _edge_key(pair: tuple[str, str]) -> str:
    return f"{pair[0]} → {pair[1]}"


def _group_edges(edges: list[Edge]) -> dict[tuple[str, str], list[Edge]]:
    groups: dict[tuple[str, str], list[Edge]] = {}
    for e in edges:
        groups.setdefault((e.from_, e.to), []).append(e)
    return groups


def _compare_edges(old: Graph, new: Graph) -> list[Change]:
    """Edge identity is the (from, to) pair. Multiple edges sharing a pair are
    compared positionally within that pair; surplus occurrences on either side
    are reported as added/removed rather than changed."""
    old_groups = _group_edges(old.edges)
    new_groups = _group_edges(new.edges)
    pairs = sorted(set(old_groups) | set(new_groups))

    added: list[Change] = []
    removed: list[Change] = []
    changed: list[Change] = []
    for pair in pairs:
        olist = old_groups.get(pair, [])
        nlist = new_groups.get(pair, [])
        key = _edge_key(pair)
        for i in range(max(len(olist), len(nlist))):
            if i < len(olist) and i < len(nlist):
                details = _attr_details(olist[i], nlist[i], EDGE_ATTRS)
                if details:
                    changed.append(Change("edge", "changed", key, details))
            elif i < len(olist):
                removed.append(Change("edge", "removed", key))
            else:
                added.append(Change("edge", "added", key))
    return added + removed + changed


def _reads_of(field_: StateField) -> frozenset[tuple[str, bool]]:
    return frozenset((r.node, r.optional) for r in field_.read)


def _compare_state(old: Graph, new: Graph) -> list[Change]:
    old_names, new_names = set(old.state), set(new.state)
    changes = [Change("state", "added", name) for name in sorted(new_names - old_names)]
    changes += [Change("state", "removed", name) for name in sorted(old_names - new_names)]
    for name in sorted(old_names & new_names):
        of, nf = old.state[name], new.state[name]
        details = _attr_details(of, nf, STATE_ATTRS)
        oreads, nreads = _reads_of(of), _reads_of(nf)
        if oreads != nreads:
            details.append(f"read: {_fmt_reads(oreads)} → {_fmt_reads(nreads)}")
        if details:
            changes.append(Change("state", "changed", name, details))
    return changes


def compare(old: Graph, new: Graph) -> list[Change]:
    """Structural comparison of two parsed graphs, in deterministic order:
    nodes added/removed/changed, then edges, then state fields."""
    return _compare_nodes(old, new) + _compare_edges(old, new) + _compare_state(old, new)


def format_text(changes: list[Change]) -> str:
    if not changes:
        return ""
    lines = []
    for c in changes:
        lines.append(f"{c.kind} {c.action}: {c.key}")
        for d in c.details:
            lines.append(f"    {d}")
    return "\n".join(lines)


def format_markdown(changes: list[Change]) -> str:
    if not changes:
        return ""
    lines = ["### graphspec diff"]
    for (kind, action), group in itertools.groupby(changes, key=lambda c: (c.kind, c.action)):
        lines.append("")
        lines.append(f"**{_KIND_TITLE[kind]} {action}**")
        for c in group:
            lines.append(f"- `{c.key}`")
            for d in c.details:
                attr, rest = d.split(": ", 1)
                old_val, new_val = rest.split(" → ", 1)
                lines.append(f"  - `{attr}`: `{old_val}` → `{new_val}`")
    return "\n".join(lines)


def run(old_path: str, new_path: str, fmt: str = "text") -> int:
    """CLI entry: parse both files, print the requested diff format, return
    the exit code (2 on parse error, 1 if the graphs differ, 0 if identical)."""
    old = load(old_path)
    new = load(new_path)
    errors = [d for d in old.parse_diagnostics if d.severity == "error"]
    errors += [d for d in new.parse_diagnostics if d.severity == "error"]
    if errors:
        for d in errors:
            print(d.format(), file=sys.stderr)
        return 2

    changes = compare(old, new)
    output = format_markdown(changes) if fmt == "markdown" else format_text(changes)
    if output:
        print(output)
    return 1 if changes else 0
