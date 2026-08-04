"""Correlation contract: every graphspec:-labelled span maps to its node."""

import json

from graphspec.parser import load
from graphspec.trace.mapping import MARKER_PREFIX, Span, correlate, parse_otlp

REFERENCE = "examples/software-delivery.yaml"
FIXTURE = "tests/fixtures/otlp-software-delivery.json"


def _fixture_spans():
    with open(FIXTURE, encoding="utf-8") as fh:
        return parse_otlp(json.load(fh))


def test_parse_otlp_flattens_and_inherits_resource_attributes():
    spans = _fixture_spans()
    assert len(spans) == 18
    assert all(s.session_id == "sess-1" for s in spans)
    llm = [s for s in spans if s.name == "claude_code.llm_request"]
    assert all(isinstance(s.attributes["gen_ai.usage.input_tokens"], int) for s in llm)


def test_every_marked_span_maps_to_its_node():
    graph = load(REFERENCE)
    spans = _fixture_spans()
    marked = [s for s in spans if s.marker is not None]
    assert marked, "fixture must carry graphspec: markers"
    corr = correlate(graph, spans)
    for s in marked:
        assert s.marker in corr.visits, f"span labelled {MARKER_PREFIX}{s.marker} unmapped"


def test_visit_counts_and_agent_name_fallback():
    corr = correlate(load(REFERENCE), _fixture_spans())
    # 4 implement executions: 3 marker-labelled + 1 matched by agent name only
    assert corr.visits == {"triage": 1, "fanout": 1, "implement": 4, "verify": 2}


def test_tokens_aggregate_under_each_unit():
    corr = correlate(load(REFERENCE), _fixture_spans())
    assert corr.tokens["triage"] == 9000 + 1200
    assert corr.tokens["implement"] == (30000 + 6000) + (28000 + 5500) + (26000 + 4000) + (24000 + 3800)
    assert corr.tokens["verify"] == (20000 + 2000) + (21000 + 2400)


def test_drift_is_reported_not_swallowed():
    corr = correlate(load(REFERENCE), _fixture_spans())
    assert any("linter" in d for d in corr.drift)
    assert len(corr.drift) == 1


def test_stopped_at_is_last_finishing_unit():
    corr = correlate(load(REFERENCE), _fixture_spans())
    assert corr.stopped_at == "verify"


def test_unexecuted_nodes_listed():
    corr = correlate(load(REFERENCE), _fixture_spans())
    assert corr.unexecuted == ["dropped", "gate", "merge", "spec"]


def test_session_filter():
    graph = load(REFERENCE)
    other = Span("x1", None, "claude_code.tool", 0, 1_000_000,
                 {"claude_code.tool.label": "graphspec:merge", "session.id": "sess-2"})
    spans = _fixture_spans() + [other]
    assert "merge" in correlate(graph, spans).visits
    assert "merge" not in correlate(graph, spans, session="sess-1").visits


def test_marker_beats_agent_name():
    graph = load(REFERENCE)
    # a span with a marker for one node and an agent name for another maps by marker
    s = Span("y1", None, "claude_code.tool", 0, 1_000_000,
             {"lbl": "graphspec:spec", "agent.name": "implementer"})
    corr = correlate(graph, [s])
    assert corr.visits == {"spec": 1}


def test_unknown_marker_is_drift():
    graph = load(REFERENCE)
    s = Span("z1", None, "claude_code.tool", 0, 1_000_000, {"lbl": "graphspec:ghost"})
    corr = correlate(graph, [s])
    assert corr.visits == {}
    assert any("ghost" in d for d in corr.drift)
