"""graphspec serve — the local editor. YAML left, live graph right.

One renderer: the browser shows SVG produced server-side by the same pipeline
as ``graphspec render``. Without Graphviz it degrades honestly to a DOT
preview with fully live validation. Binds to 127.0.0.1 only; zero external
requests; every asset vendored in ``graphspec/static/``.

The payload functions below are the testable core; the HTTP handler is a thin
JSON wrapper. ``serve``'s parse IS the CLI's parse (graphspec.parser.loads),
so the round-trip guarantee is the same code path, not a promise.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from graphspec import analysis
from graphspec.parser import loads
from graphspec.render import render_bytes, to_dot
from graphspec.trace.cost import cost_table
from graphspec.trace.mapping import correlate, parse_otlp
from graphspec.trace.overlay import overlay_dot
from graphspec.validate import run_rules

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def graphviz_available() -> bool:
    return shutil.which("dot") is not None


def _source_map(graph) -> list[dict]:
    """yaml_line -> graph element, built from the parser's line marks.

    The client resolves elements in the SVG by Graphviz's ``<title>`` content
    (node name, or ``a->b`` for edges) — no client-side YAML parsing.
    """
    entries: list[dict] = []
    for node in graph.nodes.values():
        entries.append({"kind": "node", "name": node.name, "line": node.line})
    for edge in graph.edges:
        entries.append({"kind": "edge", "from": edge.from_, "to": edge.to,
                        "title": f"{edge.from_}->{edge.to}", "line": edge.line,
                        "when": edge.when, "max": edge.max, "counter": edge.counter})
    for f in graph.state.values():
        entries.append({"kind": "state", "name": f.name, "line": f.line})
    return sorted(entries, key=lambda e: (e["line"], e["kind"], e.get("name", e.get("title", ""))))


def validate_payload(yaml_text: str, path: str = "graphspec.yaml") -> dict:
    """Same problems, same strings, as ``graphspec validate`` — by construction."""
    graph = loads(yaml_text, path)
    diags = run_rules(graph)
    return {
        "problems": [
            {"file": d.file, "line": d.line, "rule_id": d.rule_id,
             "severity": d.severity, "message": d.message, "hint": d.hint,
             "formatted": d.format()}
            for d in diags
        ],
        "valid": not any(d.severity == "error" for d in diags),
        "name": graph.name,
        "source_map": _source_map(graph),
        "state_fields": sorted(graph.state),
    }


def render_payload(yaml_text: str, path: str = "graphspec.yaml") -> dict:
    graph = loads(yaml_text, path)
    if any(d.severity == "error" for d in graph.parse_diagnostics):
        return {"error": "unparseable", "problems": [d.format() for d in graph.parse_diagnostics]}
    dot = to_dot(graph)
    if graphviz_available():
        try:
            svg = render_bytes(dot, "svg").decode("utf-8")
            return {"format": "svg", "svg": svg, "dot": dot, "source_map": _source_map(graph)}
        except subprocess.CalledProcessError:
            pass
    return {"format": "dot", "dot": dot, "source_map": _source_map(graph),
            "hint": "Graphviz 'dot' not found — DOT preview only (validation stays live). "
                    "Install from https://graphviz.org/download/ for SVG."}


def flow_payload(yaml_text: str, field: str, path: str = "graphspec.yaml") -> dict:
    """The data-flow lens: E-READ-UNSET's analysis, exposed for painting."""
    graph = loads(yaml_text, path)
    if field not in graph.state:
        return {"error": f"unknown state field '{field}'"}
    f = graph.state[field]
    writers = sorted(f.write)
    readers, optional_readers = [], []
    for name in graph.nodes:
        for ff, read in graph.reads_of(name):
            if ff.name == field:
                (optional_readers if read.optional else readers).append(name)
    before = analysis.available_before(graph)
    reach = analysis.reachable(graph)
    unset_paths = []
    for reader in sorted(set(readers)):
        if reader in reach and field not in before.get(reader, set()):
            witness = analysis.witness_unset_path(graph, reader, field)
            if witness:
                unset_paths.append(witness)
    edge_writers = sorted({e.from_ + "->" + e.to for e in graph.edges if e.counter == field})
    return {
        "field": field,
        "writers": writers,
        "edge_writers": edge_writers,
        "readers": sorted(set(readers)),
        "optional_readers": sorted(set(optional_readers)),
        "unset_paths": unset_paths,
    }


def trace_payload(yaml_text: str, otlp: dict, path: str = "graphspec.yaml",
                  session: str | None = None) -> dict:
    graph = loads(yaml_text, path)
    if any(d.severity == "error" for d in graph.parse_diagnostics):
        return {"error": "unparseable graph"}
    corr = correlate(graph, parse_otlp(otlp), session=session)
    dot = overlay_dot(graph, corr)
    payload: dict = {
        "cost_table": cost_table(graph, corr),
        "drift": list(corr.drift),
        "visits": corr.visits,
        "tokens": corr.tokens,
        "stopped_at": corr.stopped_at,
        "unexecuted": corr.unexecuted,
        "dot": dot,
    }
    if graphviz_available():
        try:
            payload["svg"] = render_bytes(dot, "svg").decode("utf-8")
            payload["format"] = "svg"
        except subprocess.CalledProcessError:
            payload["format"] = "dot"
    else:
        payload["format"] = "dot"
    return payload


class _Handler(BaseHTTPRequestHandler):
    # set by run(): the file this server owns
    file_path: str = "./graphspec.yaml"

    server_version = "graphspec"

    def log_message(self, fmt, *args):  # quiet by default
        pass

    # ------------------------------------------------------------------ util

    def _json(self, payload: dict, status: int = 200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _static(self, name: str, ctype: str):
        fpath = os.path.join(STATIC_DIR, name)
        if not os.path.isfile(fpath):
            self.send_error(404)
            return
        with open(fpath, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------------ GET

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._static("index.html", "text/html; charset=utf-8")
        elif path == "/app.js":
            self._static("app.js", "application/javascript; charset=utf-8")
        elif path == "/app.css":
            self._static("app.css", "text/css; charset=utf-8")
        elif path in ("/lens.js", "/traceoverlay.js", "/a11y.js"):
            self._static(path[1:], "application/javascript; charset=utf-8")
        elif path == "/file":
            try:
                with open(self.file_path, encoding="utf-8") as fh:
                    text = fh.read()
                mtime = os.path.getmtime(self.file_path)
            except OSError:
                text, mtime = "", 0
            self._json({"yaml": text, "mtime": mtime,
                        "name": os.path.basename(self.file_path),
                        "graphviz": graphviz_available(),
                        "examples": self._examples()})
        elif path == "/mtime":
            try:
                self._json({"mtime": os.path.getmtime(self.file_path)})
            except OSError:
                self._json({"mtime": 0})
        else:
            self.send_error(404)

    def _examples(self) -> list[dict]:
        """Shipped example templates for the empty-file picker."""
        out = []
        for name in ("software-delivery", "research-publishing", "support-triage"):
            p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "examples", f"{name}.yaml")
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as fh:
                    out.append({"name": name, "yaml": fh.read()})
        return out

    # ------------------------------------------------------------------ POST

    def do_POST(self):
        body = self._body()
        yaml_text = body.get("yaml", "")
        # the real path: impl: resolution is relative to the YAML's directory
        path = self.file_path
        if self.path == "/validate":
            self._json(validate_payload(yaml_text, path))
        elif self.path == "/render":
            self._json(render_payload(yaml_text, path))
        elif self.path == "/flow":
            self._json(flow_payload(yaml_text, body.get("field", ""), path))
        elif self.path == "/trace":
            otlp = body.get("otlp")
            if not isinstance(otlp, dict):
                self._json({"error": "otlp payload must be an OTLP JSON object"}, 400)
                return
            self._json(trace_payload(yaml_text, otlp, path, session=body.get("session")))
        elif self.path == "/save":
            try:
                with open(self.file_path, "w", encoding="utf-8") as fh:
                    fh.write(yaml_text)
                self._json({"ok": True, "mtime": os.path.getmtime(self.file_path)})
            except OSError as exc:
                self._json({"ok": False, "error": str(exc)}, 500)
        else:
            self.send_error(404)


def make_server(file_path: str, port: int) -> ThreadingHTTPServer:
    handler = type("Handler", (_Handler,), {"file_path": file_path})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def run(path: str, port: int = 8321) -> int:
    server = make_server(path, port)
    actual = server.server_address[1]
    print(f"graphspec serve: editing {path} at http://localhost:{actual} "
          f"(Graphviz {'found' if graphviz_available() else 'absent — DOT preview mode'}; Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        server.server_close()
    return 0
