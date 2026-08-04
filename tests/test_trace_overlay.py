"""Overlay contract: tint ramp, badges, greying, stop-node highlight."""

import json

from graphspec.parser import load
from graphspec.trace.mapping import correlate, parse_otlp
from graphspec.trace.overlay import overlay_dot, tint

REFERENCE = "examples/software-delivery.yaml"
FIXTURE = "tests/fixtures/otlp-software-delivery.json"


def _fixture_spans():
    with open(FIXTURE, encoding="utf-8") as fh:
        return parse_otlp(json.load(fh))


def _fixture_corr():
    return correlate(load(REFERENCE), _fixture_spans())


def _lines(dot: str) -> dict[str, str]:
    """Map each node name to its node statement line (not edge lines)."""
    result = {}
    for line in dot.splitlines():
        stripped = line.strip()
        if stripped.startswith('"'):
            end = stripped.index('"', 1)
            name = stripped[1:end]
            rest = stripped[end + 1:]
            if rest.startswith(" ["):
                result[name] = line
    return result


def test_tint_endpoints_exact():
    assert tint(0) == "#FFF5EB"
    assert tint(1) == "#F16913"


def test_tint_clamps_out_of_range():
    assert tint(-5) == tint(0)
    assert tint(5) == tint(1)


def test_overlay_unexecuted_node_is_greyed_out():
    graph = load(REFERENCE)
    corr = _fixture_corr()
    dot = overlay_dot(graph, corr)
    lines = _lines(dot)
    assert "spec" in corr.unexecuted
    line = lines["spec"]
    assert 'fillcolor="#EEEEEE"' in line
    assert 'fontcolor="#999999"' in line
    assert 'color="#BBBBBB"' in line


def test_overlay_implement_badge_shows_tokens_and_repeat_count():
    graph = load(REFERENCE)
    corr = _fixture_corr()
    dot = overlay_dot(graph, corr)
    lines = _lines(dot)
    tokens = corr.tokens["implement"]
    visits = corr.visits["implement"]
    assert visits == 4
    assert f"\\n{tokens} tok \xd7{visits}" in lines["implement"]


def test_overlay_verify_node_is_highlighted_as_stop_point():
    graph = load(REFERENCE)
    corr = _fixture_corr()
    dot = overlay_dot(graph, corr)
    lines = _lines(dot)
    assert corr.stopped_at == "verify"
    assert 'penwidth="3"' in lines["verify"]
    assert 'color="#B22222"' in lines["verify"]


def test_overlay_output_starts_with_digraph():
    graph = load(REFERENCE)
    corr = _fixture_corr()
    dot = overlay_dot(graph, corr)
    assert dot.startswith("digraph")


def test_overlay_is_deterministic():
    graph = load(REFERENCE)
    corr = _fixture_corr()
    first = overlay_dot(graph, corr)
    second = overlay_dot(graph, corr)
    assert first == second
