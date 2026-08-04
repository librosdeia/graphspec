"""DOT emitter: determinism and the frozen visual grammar."""

import subprocess
import sys

import pytest

from graphspec.parser import load, loads
from graphspec.render import CYCLE_EDGE_COLOR, to_dot

REFERENCE = "examples/software-delivery.yaml"


def test_byte_identical_across_runs():
    assert to_dot(load(REFERENCE)) == to_dot(load(REFERENCE))


def test_kind_shapes():
    dot = to_dot(load(REFERENCE))
    assert '"fanout" [shape="box"' in dot                      # function
    assert 'style="rounded,filled"' in dot                     # llm
    assert 'peripheries="2"' in dot                            # subagent double border
    assert '"gate" [shape="diamond"' in dot                    # human
    assert 'shape="doublecircle"' in dot                       # terminal


def test_conditional_edges_dashed_with_when_label():
    dot = to_dot(load(REFERENCE))
    assert '"triage" -> "spec" [style="dashed", label="category == \'feature\'"];' in dot
    # unconditional edge has no attributes at all
    assert '"spec" -> "fanout";' in dot


def test_capped_edges_distinct_colour_and_max_label():
    dot = to_dot(load(REFERENCE))
    line = next(l for l in dot.splitlines() if '"verify" -> "implement"' in l)
    assert CYCLE_EDGE_COLOR in line
    assert "max=3" in line


def test_synthetic_on_exhausted_edges_drawn():
    dot = to_dot(load(REFERENCE))
    line = next(l for l in dot.splitlines()
                if '"verify" -> "gate"' in l and "on_exhausted" in l)
    assert CYCLE_EDGE_COLOR in line


def test_badges_shape_encoded():
    dot = to_dot(load(REFERENCE))
    implement = next(l for l in dot.splitlines() if l.strip().startswith('"implement"'))
    assert "⧉" in implement and "∥3" in implement and "⚡" in implement
    verify = next(l for l in dot.splitlines() if l.strip().startswith('"verify"'))
    assert "∀ verify" in verify
    # checkpointed nodes carry a tick on the label's last line
    spec = next(l for l in dot.splitlines() if l.strip().startswith('"spec"'))
    assert "\\n✓" in spec


def test_entry_and_terminals_ranked():
    dot = to_dot(load(REFERENCE))
    assert '{rank=source; "triage";}' in dot
    assert '{rank=sink; "dropped" "merge";}' in dot


def test_substrate_clusters_when_more_than_one():
    g = loads(
        "graphspec: 1\nname: multi\nentry: a\nterminals: [b]\n"
        "nodes:\n  a: {kind: llm, substrate: workflow}\n"
        "  b: {kind: terminal, substrate: channel}\n"
        "edges:\n  - {from: a, to: b}\n"
    )
    dot = to_dot(g)
    assert 'subgraph "cluster_workflow"' in dot
    assert 'subgraph "cluster_channel"' in dot
    # single-substrate graphs stay uncustered
    assert "subgraph" not in to_dot(load(REFERENCE))


def test_cli_render_prints_dot(tmp_path, capsys, monkeypatch):
    from graphspec.render import run
    assert run(REFERENCE, fmt="dot") == 0
    out = capsys.readouterr().out
    assert out.startswith('digraph "software-delivery" {')
    assert out.endswith("}\n")


def test_svg_fails_with_install_hint_when_dot_absent(monkeypatch, capsys):
    from graphspec import render

    def missing(*a, **k):
        raise FileNotFoundError("dot")

    monkeypatch.setattr(render.subprocess, "run", missing)
    assert render.run(REFERENCE, fmt="svg") == 1
    assert "graphviz.org" in capsys.readouterr().err
