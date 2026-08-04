"""Foundation tests: diagnostics, model, parser, expr, analysis."""

import pytest

from graphspec.diagnostics import Diagnostic, sort_diagnostics
from graphspec.expr import ExprError, identifiers, parse_when
from graphspec.model import Edge, Graph, Node, Read, StateField, parse_read
from graphspec.parser import load, loads
from graphspec import analysis

REFERENCE = "examples/software-delivery.yaml"


# ---------------------------------------------------------------- diagnostics

def test_diagnostic_format_with_hint():
    d = Diagnostic("g.yaml", 12, "E-EDGE-ENDS", "error", "edge points at undeclared node 'x'",
                   "declare 'x' under nodes: or fix the typo")
    assert d.format() == (
        "g.yaml:12: [E-EDGE-ENDS] edge points at undeclared node 'x'\n"
        "  hint: declare 'x' under nodes: or fix the typo"
    )


def test_diagnostic_sorting_is_stable():
    a = Diagnostic("g.yaml", 5, "E-KIND", "error", "m")
    b = Diagnostic("g.yaml", 2, "E-HUMAN", "error", "m")
    assert [d.line for d in sort_diagnostics([a, b])] == [2, 5]


# ---------------------------------------------------------------------- model

def test_parse_read_optional_suffix():
    assert parse_read("verify?") == Read("verify", optional=True)
    assert parse_read("verify") == Read("verify", optional=False)


def _tiny_graph():
    g = Graph(path="t.yaml", entry="a", terminals=["end"])
    g.nodes = {
        "a": Node("a", "llm", line=1),
        "gate": Node("gate", "human", line=2, timeout="48h", on_timeout="end",
                     presents=["score"]),
        "end": Node("end", "terminal", line=3),
    }
    g.edges = [
        Edge("a", "gate", line=10),
        Edge("gate", "a", line=11, max=2, counter="tries", on_exhausted="end"),
    ]
    g.state = {
        "score": StateField("score", "number", write=["a"], read=[Read("gate")]),
        "tries": StateField("tries", "number"),
    }
    return g


def test_synthetic_edges_from_on_timeout_and_on_exhausted():
    g = _tiny_graph()
    synth = g.synthetic_edges()
    assert ("gate", "end", "on_timeout") in [(e.from_, e.to, e.synthetic) for e in synth]
    assert ("gate", "end", "on_exhausted") in [(e.from_, e.to, e.synthetic) for e in synth]
    # reserved words produce no synthetic edge
    g.nodes["gate"].on_timeout = "escalate"
    g.edges[1].on_exhausted = "fail"
    assert g.synthetic_edges() == []


def test_presents_makes_reads_optional():
    g = _tiny_graph()
    reads = g.reads_of("gate")
    assert [(f.name, r.optional) for f, r in reads] == [("score", True)]


def test_capped_edge_requires_all_three():
    assert Edge("a", "b", max=2, counter="c", on_exhausted="end").capped
    assert not Edge("a", "b", max=2, counter="c").capped


# --------------------------------------------------------------------- parser

def test_reference_example_parses_with_lines():
    g = load(REFERENCE)
    assert [d for d in g.parse_diagnostics if d.severity == "error"] == []
    assert g.name == "software-delivery"
    assert g.entry == "triage"
    assert g.terminals == ["merge", "dropped"]
    assert set(g.nodes) == {"triage", "spec", "fanout", "implement", "verify", "gate", "merge", "dropped"}
    assert len(g.edges) == 10
    assert all(n.line > 0 for n in g.nodes.values())
    assert all(e.line > 0 for e in g.edges)
    assert all(f.line > 0 for f in g.state.values())
    # spot-check semantics
    assert g.nodes["implement"].fan_out_over == "branches"
    assert g.nodes["implement"].as_ == "branch"
    assert g.state["spec"].read == [Read("implement", True), Read("verify", True)]
    capped = [e for e in g.edges if e.capped]
    assert {(e.from_, e.to) for e in capped} == {("verify", "implement"), ("gate", "fanout")}


def test_unknown_key_is_warning_not_error():
    g = loads("graphspec: 1\nname: x\nentry: a\nterminals: [a]\ncolour: red\n"
              "nodes:\n  a: {kind: terminal, frobnicate: 3}\n")
    warnings = [d for d in g.parse_diagnostics if d.rule_id == "W-UNKNOWN-KEY"]
    assert len(warnings) == 2
    assert all(d.severity == "warning" for d in warnings)


def test_enum_without_values_is_error():
    g = loads("graphspec: 1\nname: x\nentry: a\nterminals: [a]\n"
              "state:\n  cat: {type: enum, write: [a]}\nnodes:\n  a: {kind: terminal}\n")
    assert any("requires 'values'" in d.message and d.severity == "error"
               for d in g.parse_diagnostics)


def test_unparseable_yaml_yields_single_error_with_line():
    g = loads("graphspec: 1\nname: [unclosed\n  bad: {")
    errors = [d for d in g.parse_diagnostics if d.severity == "error"]
    assert len(errors) == 1
    assert errors[0].rule_id == "E-PARSE"
    assert errors[0].line > 0
    assert g.nodes == {}


def test_missing_version_key_is_error():
    g = loads("name: x\nentry: a\nterminals: [a]\nnodes:\n  a: {kind: terminal}\n")
    assert any("graphspec" in d.message and d.severity == "error" for d in g.parse_diagnostics)


# ----------------------------------------------------------------------- expr

@pytest.mark.parametrize("src,idents", [
    ("category == 'feature'", {"category"}),
    ("verdict == 'fail'", {"verdict"}),
    ("a < 3 && (b >= 2 || !c)", {"a", "b", "c"}),
    ("done == true", {"done"}),
    ("x != -1", {"x"}),
])
def test_valid_expressions(src, idents):
    parse_when(src)
    assert identifiers(src) == idents


@pytest.mark.parametrize("src", [
    "a + b == 3",            # arithmetic
    "len(a) == 3",           # function call
    "a[0] == 'x'",           # indexing
    'category == "feature"', # double quotes
    "a ==",                  # incomplete
    "a == 'unterminated",    # unterminated string
])
def test_invalid_expressions_raise(src):
    with pytest.raises(ExprError):
        parse_when(src)


def test_true_false_are_literals_not_identifiers():
    assert identifiers("flag == true || other == false") == {"flag", "other"}


# ------------------------------------------------------------------- analysis

def test_reachability_counts_synthetic_edges():
    g = Graph(path="t", entry="a", terminals=["z"])
    g.nodes = {n: Node(n, "function") for n in ("a", "b", "z")}
    g.nodes["a"].kind = "human"
    g.nodes["a"].on_timeout = "b"          # only path to b is synthetic
    g.edges = [Edge("a", "z")]
    assert analysis.reachable(g) == {"a", "b", "z"}


def test_nodes_reaching_terminals():
    g = Graph(path="t", entry="a", terminals=["z"])
    g.nodes = {n: Node(n, "function") for n in ("a", "orphan", "z")}
    g.edges = [Edge("a", "z"), Edge("orphan", "orphan")]
    assert analysis.nodes_reaching_terminals(g) == {"a", "z"}


def test_uncapped_cycle_found_and_capped_cycle_ok():
    g = Graph(path="t", entry="a", terminals=["z"])
    g.nodes = {n: Node(n, "function") for n in ("a", "b", "z")}
    g.edges = [Edge("a", "b"), Edge("b", "a"), Edge("b", "z")]
    cycle = analysis.uncapped_cycle(g)
    assert cycle is not None and cycle[0] == cycle[-1]
    g.edges[1] = Edge("b", "a", max=3, counter="tries", on_exhausted="z")
    assert analysis.uncapped_cycle(g) is None


def test_guaranteed_writes_intersect_over_paths():
    # a writes x only on one branch; d reads it -> not guaranteed
    g = Graph(path="t", entry="a", terminals=["d"])
    g.nodes = {n: Node(n, "function") for n in ("a", "b", "c", "d")}
    g.edges = [Edge("a", "b"), Edge("a", "c"), Edge("b", "d"), Edge("c", "d")]
    g.state = {"x": StateField("x", "string", write=["b"], read=[Read("d")])}
    before = analysis.available_before(g)
    assert "x" not in before["d"]
    # once c also writes it, both paths carry it
    g.state["x"].write.append("c")
    assert "x" in analysis.available_before(g)["d"]


def test_counters_available_from_run_start():
    g = Graph(path="t", entry="a", terminals=["b"])
    g.nodes = {n: Node(n, "function") for n in ("a", "b")}
    g.edges = [Edge("a", "b", max=1, counter="tries", on_exhausted="b")]
    g.state = {"tries": StateField("tries", "number", read=[Read("b")])}
    assert "tries" in analysis.available_before(g)["b"]


def test_own_writes_visible_to_outgoing_edges():
    g = Graph(path="t", entry="a", terminals=["b"])
    g.nodes = {n: Node(n, "function") for n in ("a", "b")}
    g.edges = [Edge("a", "b", when="cat == 'x'")]
    g.state = {"cat": StateField("cat", "string", write=["a"])}
    assert "cat" in analysis.available_after(g)["a"]
    assert "cat" in analysis.available_before(g)["b"]


def test_witness_unset_path_names_the_gap():
    g = Graph(path="t", entry="a", terminals=["d"])
    g.nodes = {n: Node(n, "function") for n in ("a", "b", "c", "d")}
    g.edges = [Edge("a", "b"), Edge("a", "c"), Edge("b", "d"), Edge("c", "d")]
    g.state = {"x": StateField("x", "string", write=["b"], read=[Read("d")])}
    path = analysis.witness_unset_path(g, "d", "x")
    assert path == ["a", "c", "d"]
    # no witness when every path writes
    g.state["x"].write.append("c")
    assert analysis.witness_unset_path(g, "d", "x") == []
