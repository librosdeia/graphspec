"""Trace overlay — restyle a graph's DOT rendering with execution facts.

Consumes a :class:`graphspec.trace.mapping.Correlation` and produces DOT text
via the one renderer (:func:`graphspec.render.to_dot`), never emitting its own
node or edge statements. All styling flows through ``to_dot``'s two hooks:
``overrides`` (DOT attribute overrides per node) and ``label_suffixes`` (text
appended to a node's label).

Visual grammar (PRD):
- Unexecuted nodes are greyed out.
- Executed nodes are tinted in proportion to their share of token cost
  (sequential ramp, ``#FFF5EB`` -> ``#F16913``), and always carry a numeric
  token badge in the label — cost is never conveyed by tint alone.
- Repeat visits add a ``×N`` suffix after the token badge.
- The node where the run stopped is additionally outlined.
"""

from __future__ import annotations

from graphspec.model import Graph
from graphspec.render import to_dot
from graphspec.trace.mapping import Correlation

UNEXECUTED_OVERRIDE = {
    "fillcolor": "#EEEEEE",
    "fontcolor": "#999999",
    "color": "#BBBBBB",
}

TINT_START = (0xFF, 0xF5, 0xEB)  # #FFF5EB, ratio 0
TINT_END = (0xF1, 0x69, 0x13)    # #F16913, ratio 1

STOPPED_AT_OVERRIDE = {
    "penwidth": "3",
    "color": "#B22222",
}


def tint(ratio: float) -> str:
    """Sequential fill colour for *ratio* in [0, 1], clamped at the edges."""
    ratio = 0.0 if ratio < 0.0 else 1.0 if ratio > 1.0 else ratio
    r, g, b = (round(s + (e - s) * ratio) for s, e in zip(TINT_START, TINT_END))
    return f"#{r:02X}{g:02X}{b:02X}"


def overlay_dot(graph: Graph, corr: Correlation) -> str:
    """DOT for *graph* restyled with *corr*'s execution facts."""
    overrides: dict[str, dict[str, str]] = {}
    label_suffixes: dict[str, str] = {}

    max_tokens = corr.max_tokens()

    for node in corr.unexecuted:
        overrides[node] = dict(UNEXECUTED_OVERRIDE)

    for node, visits in corr.visits.items():
        tokens = corr.tokens.get(node, 0)
        ratio = tokens / max_tokens if max_tokens else 0.0
        overrides[node] = {"fillcolor": tint(ratio)}
        suffix = f"\\n{tokens} tok"
        if visits > 1:
            suffix += f" ×{visits}"
        label_suffixes[node] = suffix

    if corr.stopped_at is not None:
        overrides.setdefault(corr.stopped_at, {}).update(STOPPED_AT_OVERRIDE)

    return to_dot(graph, overrides=overrides, label_suffixes=label_suffixes)
