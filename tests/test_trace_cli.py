"""`graphspec trace` end-to-end: parse graph, load OTLP, correlate, emit DOT + cost table."""

import json

from graphspec.trace.cli import run

REFERENCE = "examples/software-delivery.yaml"
FIXTURE = "tests/fixtures/otlp-software-delivery.json"


def test_run_emits_dot_then_prefixed_cost_table(capsys):
    rc = run(REFERENCE, FIXTURE)
    out, err = capsys.readouterr()
    assert rc == 0
    assert err == ""
    assert out.startswith("digraph")
    lines = out.splitlines()
    comment_lines = [l for l in lines if l.startswith("// ")]
    assert comment_lines, "cost table must be emitted as DOT line comments"
    assert any("linter" in l for l in comment_lines), "drift must be reported in the output"


def test_run_nonexistent_otlp_path_returns_1(capsys):
    rc = run(REFERENCE, "tests/fixtures/does-not-exist.json")
    out, err = capsys.readouterr()
    assert rc == 1
    assert err.strip() != ""
    assert "does-not-exist.json" in err


def test_run_malformed_json_returns_1(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    rc = run(REFERENCE, str(bad))
    out, err = capsys.readouterr()
    assert rc == 1
    assert err.strip() != ""


def test_run_bad_graph_path_returns_1(capsys):
    rc = run("no/such/graphspec.yaml", FIXTURE)
    out, err = capsys.readouterr()
    assert rc == 1
    assert err.strip() != ""


def test_session_filter_reaches_correlate():
    # sess-1 is the fixture's own session id; filtering to it keeps every
    # marker- and agent-mapped span, so implement is still visited 4 times.
    import graphspec.trace.cli as cli_mod

    captured = {}
    real_correlate = None

    from graphspec.trace import mapping as mapping_mod

    real_correlate = mapping_mod.correlate

    def spy(graph, spans, session=None):
        corr = real_correlate(graph, spans, session=session)
        captured["visits"] = dict(corr.visits)
        captured["session"] = session
        return corr

    mapping_mod.correlate = spy
    try:
        rc = run(REFERENCE, FIXTURE, session="sess-1")
    finally:
        mapping_mod.correlate = real_correlate

    assert rc == 0
    assert captured["session"] == "sess-1"
    assert captured["visits"]["implement"] == 4


def test_load_otlp_http_branch(monkeypatch):
    from graphspec.trace.inputs import load_otlp

    with open(FIXTURE, encoding="utf-8") as fh:
        payload = fh.read()

    class _FakeResponse:
        def __init__(self, body: bytes):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(url, timeout=10):
        assert url == "http://collector.example/v1/traces/query"
        assert timeout == 10
        return _FakeResponse(payload.encode("utf-8"))

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    data = load_otlp("http://collector.example/v1/traces/query")
    assert "resourceSpans" in data
