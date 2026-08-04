"""serve: payload core + HTTP wrapper. The round-trip test guards the shared parse."""

import glob
import http.client
import json
import pathlib
import threading

import pytest

from graphspec.parser import load
from graphspec.serve import (
    flow_payload, make_server, render_payload, trace_payload, validate_payload,
)
from graphspec.validate import run_rules

REFERENCE = "examples/software-delivery.yaml"


def _text(path):
    return pathlib.Path(path).read_text(encoding="utf-8")


# ------------------------------------------------------------------ round-trip

@pytest.mark.parametrize("path", sorted(glob.glob("examples/broken-e-*.yaml")))
def test_round_trip_serve_and_cli_agree(path):
    """/validate problems == CLI validate problems: same rule IDs, same lines,
    same strings — they literally share the code path."""
    cli = [d.format() for d in run_rules(load(path))]
    served = [p["formatted"] for p in validate_payload(_text(path), path)["problems"]]
    assert served == cli


def test_reference_is_valid_with_source_map_and_fields():
    payload = validate_payload(_text(REFERENCE), REFERENCE)
    assert payload["valid"] is True
    assert payload["problems"] == []
    assert payload["name"] == "software-delivery"
    assert payload["state_fields"] == sorted(load(REFERENCE).state)
    nodes = [e for e in payload["source_map"] if e["kind"] == "node"]
    assert {n["name"] for n in nodes} == set(load(REFERENCE).nodes)
    assert all(n["line"] > 0 for n in nodes)


def test_unparseable_yaml_is_a_problem_not_a_crash():
    payload = validate_payload("graphspec: 1\nname: [unclosed", "x.yaml")
    assert payload["valid"] is False
    assert payload["problems"][0]["rule_id"] == "E-PARSE"


# --------------------------------------------------------------------- render

def test_render_payload_degrades_honestly_without_graphviz(monkeypatch):
    import graphspec.serve as serve_mod
    monkeypatch.setattr(serve_mod, "graphviz_available", lambda: False)
    payload = render_payload(_text(REFERENCE), REFERENCE)
    assert payload["format"] == "dot"
    assert payload["dot"].startswith('digraph "software-delivery"')
    assert "graphviz.org" in payload["hint"]
    assert payload["source_map"]


def test_render_payload_matches_cli_dot():
    from graphspec.render import to_dot
    payload = render_payload(_text(REFERENCE), REFERENCE)
    assert payload["dot"] == to_dot(load(REFERENCE))


# ----------------------------------------------------------------------- flow

def test_flow_payload_is_the_lens_contract():
    payload = flow_payload(_text(REFERENCE), "spec", REFERENCE)
    assert payload["writers"] == ["gate", "spec"]
    # gate reads 'spec' optionally via its presents: list
    assert payload["optional_readers"] == ["gate", "implement", "verify"]
    assert payload["readers"] == []
    assert payload["unset_paths"] == []


def test_flow_payload_reports_unset_paths():
    yaml_text = (
        "graphspec: 1\nname: d\nentry: a\nterminals: [d]\n"
        "state:\n  x: {type: string, write: [b], read: [d]}\n"
        "nodes:\n  a: {kind: llm}\n  b: {kind: llm}\n  c: {kind: llm}\n  d: {kind: terminal}\n"
        "edges:\n  - {from: a, to: b}\n  - {from: a, to: c}\n  - {from: b, to: d}\n  - {from: c, to: d}\n"
    )
    payload = flow_payload(yaml_text, "x")
    assert payload["unset_paths"] == [["a", "c", "d"]]


def test_flow_payload_counter_edge_writers():
    payload = flow_payload(_text(REFERENCE), "attempts", REFERENCE)
    assert payload["edge_writers"] == ["verify->implement"]
    assert payload["unset_paths"] == []


def test_flow_unknown_field():
    assert "error" in flow_payload(_text(REFERENCE), "nope", REFERENCE)


# ---------------------------------------------------------------------- trace

def test_trace_payload_overlay_and_table():
    otlp = json.loads(_text("tests/fixtures/otlp-software-delivery.json"))
    payload = trace_payload(_text(REFERENCE), otlp, REFERENCE)
    assert payload["stopped_at"] == "verify"
    assert payload["visits"]["implement"] == 4
    assert "implement" in payload["cost_table"]
    assert any("linter" in d for d in payload["drift"])
    assert payload["dot"].startswith("digraph")


# ------------------------------------------------------------------- HTTP end

@pytest.fixture()
def server(tmp_path):
    import shutil
    f = tmp_path / "graphspec.yaml"
    f.write_text(_text(REFERENCE), encoding="utf-8")
    shutil.copytree("examples/scripts", tmp_path / "scripts")
    srv = make_server(str(f), 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv, str(f)
    srv.shutdown()
    srv.server_close()


def _request(srv, method, path, body=None):
    port = srv.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    payload = json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload,
                 headers={"Content-Type": "application/json"} if payload else {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def test_http_binds_localhost_and_serves_endpoints(server):
    srv, fpath = server
    assert srv.server_address[0] == "127.0.0.1"
    status, data = _request(srv, "GET", "/file")
    assert status == 200
    doc = json.loads(data)
    assert doc["name"] == "graphspec.yaml"
    assert len(doc["examples"]) == 3

    status, data = _request(srv, "POST", "/validate", {"yaml": doc["yaml"]})
    assert status == 200 and json.loads(data)["valid"] is True

    status, data = _request(srv, "POST", "/render", {"yaml": doc["yaml"]})
    assert status == 200 and json.loads(data)["format"] in ("svg", "dot")

    status, data = _request(srv, "POST", "/flow", {"yaml": doc["yaml"], "field": "spec"})
    assert status == 200 and json.loads(data)["writers"] == ["gate", "spec"]


def test_http_save_owns_the_file_handle(server):
    srv, fpath = server
    new_text = _text(REFERENCE) + "\n# edited\n"
    status, data = _request(srv, "POST", "/save", {"yaml": new_text})
    assert status == 200 and json.loads(data)["ok"] is True
    assert pathlib.Path(fpath).read_text(encoding="utf-8") == new_text
    status, data = _request(srv, "GET", "/mtime")
    assert json.loads(data)["mtime"] > 0


def test_http_serves_static_page(server):
    srv, _ = server
    status, data = _request(srv, "GET", "/")
    assert status == 200
    text = data.decode("utf-8")
    assert "<title>graphspec" in text
    # no external requests: no http(s) URLs in fetches/links (file is self-contained)
    assert "https://cdn" not in text and "http://cdn" not in text


def test_http_404_on_unknown(server):
    srv, _ = server
    status, _ = _request(srv, "GET", "/etc/passwd")
    assert status == 404
