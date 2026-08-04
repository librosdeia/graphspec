"""cost_table: fixed-width per-node cost summary printed to stdout by the CLI."""

import json

from graphspec.parser import load
from graphspec.trace.cost import cost_table
from graphspec.trace.mapping import correlate, parse_otlp

REFERENCE = "examples/software-delivery.yaml"
FIXTURE = "tests/fixtures/otlp-software-delivery.json"


def _fixture_corr():
    graph = load(REFERENCE)
    with open(FIXTURE, encoding="utf-8") as fh:
        spans = parse_otlp(json.load(fh))
    return graph, correlate(graph, spans)


def test_implement_row_shows_visits_and_tokens():
    graph, corr = _fixture_corr()
    table = cost_table(graph, corr)
    lines = table.splitlines()
    implement_line = next(l for l in lines if l.startswith("implement"))
    fields = implement_line.split()
    assert fields[0] == "implement"
    assert fields[1] == str(corr.visits["implement"])
    assert fields[2] == str(corr.tokens["implement"])
    assert corr.visits["implement"] == 4


def test_total_row_sums_visits_and_tokens():
    graph, corr = _fixture_corr()
    table = cost_table(graph, corr)
    lines = table.splitlines()
    total_line = next(l for l in lines if l.startswith("TOTAL"))
    fields = total_line.split()
    assert fields[0] == "TOTAL"
    assert int(fields[1]) == sum(corr.visits.values())
    assert int(fields[2]) == sum(corr.tokens.values())
    assert sum(corr.visits.values()) == 8


def test_total_latency_sums_all_node_latency():
    graph, corr = _fixture_corr()
    table = cost_table(graph, corr)
    total_line = next(l for l in table.splitlines() if l.startswith("TOTAL"))
    latency_field = total_line.split()[-1]
    assert latency_field.endswith("s")
    expected_seconds = round(sum(corr.latency_ms.values()) / 1000.0, 1)
    assert float(latency_field[:-1]) == expected_seconds


def test_not_executed_line_present():
    graph, corr = _fixture_corr()
    table = cost_table(graph, corr)
    assert "not executed: dropped, gate, merge, spec" in table.splitlines()


def test_drift_line_mentions_linter():
    graph, corr = _fixture_corr()
    table = cost_table(graph, corr)
    drift_lines = [l for l in table.splitlines() if l.startswith("drift: ")]
    assert drift_lines
    assert any("linter" in l for l in drift_lines)
    # phrased as a feature, not an error
    for l in drift_lines:
        assert "error" not in l.lower()
        assert "fail" not in l.lower()


def test_rows_sorted_by_tokens_descending_ties_by_name():
    graph, corr = _fixture_corr()
    table = cost_table(graph, corr)
    lines = table.splitlines()
    # header, separator, then N rows for executed nodes, then TOTAL
    node_lines = lines[2:2 + len(corr.visits)]
    names = [l.split()[0] for l in node_lines]
    expected_order = sorted(corr.visits.keys(), key=lambda n: (-corr.tokens.get(n, 0), n))
    assert names == expected_order


def test_header_and_separator_present():
    graph, corr = _fixture_corr()
    table = cost_table(graph, corr)
    lines = table.splitlines()
    assert lines[0].split() == ["node", "visits", "tokens", "latency"]
    assert set(lines[1]) == {"-"}
    assert len(lines[1]) == len(lines[0])


def test_columns_are_padded_and_aligned():
    graph, corr = _fixture_corr()
    table = cost_table(graph, corr)
    lines = table.splitlines()
    # every row up to and including TOTAL shares the same line length
    row_lines = lines[: 3 + len(corr.visits)]  # header, sep, N rows, TOTAL
    lengths = {len(l) for l in row_lines}
    assert len(lengths) == 1


def test_ends_with_single_trailing_newline():
    graph, corr = _fixture_corr()
    table = cost_table(graph, corr)
    assert table.endswith("\n")
    assert not table.endswith("\n\n")


def test_deterministic_byte_identical_across_calls():
    graph, corr = _fixture_corr()
    table1 = cost_table(graph, corr)
    table2 = cost_table(graph, corr)
    assert table1 == table2


def test_only_executed_nodes_get_a_row():
    graph, corr = _fixture_corr()
    table = cost_table(graph, corr)
    lines = table.splitlines()
    node_lines = lines[2:2 + len(corr.visits)]
    names = {l.split()[0] for l in node_lines}
    assert names == set(corr.visits.keys())
    for unexecuted_node in corr.unexecuted:
        assert unexecuted_node not in names


def test_no_unexecuted_and_no_drift_omits_those_lines():
    graph = load(REFERENCE)
    # a correlation with no unexecuted nodes and no drift at all
    from graphspec.trace.mapping import Correlation

    corr = Correlation(
        visits={"triage": 1},
        tokens={"triage": 500},
        latency_ms={"triage": 1200.0},
        stopped_at="triage",
        drift=[],
        unexecuted=[],
    )
    table = cost_table(graph, corr)
    lines = table.splitlines()
    assert not any(l.startswith("not executed:") for l in lines)
    assert not any(l.startswith("drift:") for l in lines)
    # header, separator, one node row, TOTAL row = 4 lines exactly
    assert len(lines) == 4
