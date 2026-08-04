"""Graphviz DOT emitter — the one renderer.

The CLI, the golden files, the book figures and the serve editor all come from
this module; the editor is a view, never a second layout implementation.

Visual grammar (frozen — the book prints these figures):
- Shape and colour by kind: function rectangle, llm rounded box, subagent
  double border, human diamond with a distinct fill, terminal doubled circle.
- Unconditional edges solid; conditional edges dashed, labelled with the when.
- Cycle-capping edges and on_timeout/on_exhausted edges in a distinct colour,
  labelled max=N where applicable.
- Badges, all shape-encoded, never colour-only: effects: external carries ⚡;
  fan_out_over nodes a stacked-card marker ⧉ plus ∥N when concurrency is set;
  join nodes a glyph before the label (∀ all, ∃ any, ½ majority, 1 first);
  checkpointed nodes a tick ✓ on the bottom line of the label.
- More than one substrate present -> nodes grouped in labelled clusters.
- entry anchored at the top, terminals at the bottom.

Determinism: rendering the same file twice produces byte-identical DOT —
sorted nodes, declaration-ordered edges, no timestamps.
"""

from __future__ import annotations

import subprocess
import sys

from graphspec.model import Edge, Graph, Node
from graphspec.parser import load

INSTALL_HINT = ("Graphviz 'dot' not found — install it to emit SVG/PNG "
                "(https://graphviz.org/download/, e.g. `brew install graphviz` "
                "or `apt install graphviz`); DOT output needs no install")

_KIND_ATTRS = {
    "function": {"shape": "box", "style": "filled", "fillcolor": "#F2F2F2"},
    "llm": {"shape": "box", "style": "rounded,filled", "fillcolor": "#DDEBF7"},
    "subagent": {"shape": "box", "peripheries": "2", "style": "filled", "fillcolor": "#E6F2E6"},
    "human": {"shape": "diamond", "style": "filled", "fillcolor": "#FDE9C8"},
    "terminal": {"shape": "doublecircle", "style": "filled", "fillcolor": "#F2F2F2"},
}
_UNKNOWN_KIND_ATTRS = {"shape": "box", "style": "filled,dashed", "fillcolor": "#FFFFFF"}

CYCLE_EDGE_COLOR = "#B22222"

_JOIN_GLYPH = {"all": "∀", "any": "∃", "majority": "½", "first": "1"}


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _attrs(d: dict[str, str]) -> str:
    return "[" + ", ".join(f"{k}={_q(v)}" for k, v in d.items()) + "]"


def node_label(graph: Graph, node: Node) -> str:
    """The node's label with its shape-encoded badges."""
    prefix = ""
    if node.join in _JOIN_GLYPH:
        prefix = _JOIN_GLYPH[node.join] + " "
    label = prefix + node.name
    suffix = ""
    if node.fan_out_over:
        suffix += " ⧉"
        if node.concurrency:
            suffix += f"∥{node.concurrency}"
    if node.effects == "external":
        suffix += " ⚡"
    label += suffix
    if node.name in graph.checkpoints_after:
        label += "\\n✓"
    return label


def _node_stmt(graph: Graph, node: Node) -> str:
    attrs = dict(_KIND_ATTRS.get(node.kind, _UNKNOWN_KIND_ATTRS))
    attrs["label"] = node_label(graph, node)
    return f"  {_q(node.name)} {_attrs(attrs)};"


def edge_attrs(edge: Edge) -> dict[str, str]:
    attrs: dict[str, str] = {}
    labels: list[str] = []
    if edge.synthetic:
        attrs["color"] = CYCLE_EDGE_COLOR
        attrs["style"] = "dashed"
        labels.append(edge.synthetic)
    else:
        if edge.when:
            attrs["style"] = "dashed"
            labels.append(edge.when)
        if edge.capped:
            attrs["color"] = CYCLE_EDGE_COLOR
            labels.append(f"max={edge.max}")
    if labels:
        attrs["label"] = "\\n".join(labels)
    return attrs


def _edge_stmt(edge: Edge) -> str:
    attrs = edge_attrs(edge)
    suffix = f" {_attrs(attrs)}" if attrs else ""
    return f"  {_q(edge.from_)} -> {_q(edge.to)}{suffix};"


def to_dot(graph: Graph) -> str:
    """Deterministic DOT for *graph* (same input -> byte-identical output)."""
    lines: list[str] = []
    name = graph.name or "graphspec"
    lines.append(f"digraph {_q(name)} {{")
    lines.append("  rankdir=TB;")
    lines.append('  node [fontname="Helvetica", fontsize=11];')
    lines.append('  edge [fontname="Helvetica", fontsize=9];')

    substrates = sorted({graph.effective_substrate(n) for n in graph.nodes.values()})
    clustered = len(substrates) > 1

    if clustered:
        for substrate in substrates:
            lines.append(f"  subgraph {_q('cluster_' + substrate)} {{")
            lines.append(f"    label={_q('substrate: ' + substrate)};")
            lines.append('    style=dashed; color="#888888";')
            for nname in sorted(graph.nodes):
                node = graph.nodes[nname]
                if graph.effective_substrate(node) == substrate:
                    lines.append("  " + _node_stmt(graph, node))
            lines.append("  }")
    else:
        for nname in sorted(graph.nodes):
            lines.append(_node_stmt(graph, graph.nodes[nname]))
        # entry at the top, terminals at the bottom (global ranks fight
        # clusters, so they are emitted only in the unclustered layout)
        if graph.entry in graph.nodes:
            lines.append(f"  {{rank=source; {_q(graph.entry)};}}")
        terminals = [t for t in sorted(set(graph.terminals)) if t in graph.nodes]
        if terminals:
            lines.append(f"  {{rank=sink; {' '.join(_q(t) for t in terminals)};}}")

    for edge in graph.edges:
        lines.append(_edge_stmt(edge))
    for edge in sorted(graph.synthetic_edges(), key=lambda e: (e.from_, e.to, e.synthetic or "")):
        lines.append(_edge_stmt(edge))

    lines.append("}")
    return "\n".join(lines) + "\n"


def render_bytes(dot: str, fmt: str) -> bytes:
    """Shell out to Graphviz for svg/png. Raises FileNotFoundError when absent."""
    result = subprocess.run(
        ["dot", f"-T{fmt}"], input=dot.encode("utf-8"),
        capture_output=True, check=True,
    )
    return result.stdout


def run(path: str, fmt: str = "dot") -> int:
    graph = load(path)
    errors = [d for d in graph.parse_diagnostics if d.severity == "error"]
    if errors:
        for d in errors:
            print(d.format(), file=sys.stderr)
        return 1
    dot = to_dot(graph)
    if fmt == "dot":
        sys.stdout.write(dot)
        return 0
    try:
        payload = render_bytes(dot, fmt)
    except FileNotFoundError:
        print(INSTALL_HINT, file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr.decode("utf-8", "replace"))
        return 1
    sys.stdout.buffer.write(payload)
    return 0
