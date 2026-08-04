"""UI-SPEC acceptance checks (the headlessly-verifiable ones).

Round-trip parity lives in test_serve.py (same code path by construction).
The keyboard-only walkthrough is a manual check; its structural prerequisites
are asserted by the per-module static tests.
"""

import glob
import os
import re
import shutil
import subprocess

import pytest

from graphspec.parser import load
from graphspec.render import to_dot
from graphspec.serve import render_payload, validate_payload

REFERENCE = "examples/software-delivery.yaml"
STATIC = "graphspec/static"


def test_vendored_payload_under_3mb():
    total = sum(os.path.getsize(p) for p in glob.glob(f"{STATIC}/*"))
    assert total < 3 * 1024 * 1024, f"static payload {total} bytes exceeds the 3 MB budget"


def test_no_external_requests_in_static_assets():
    """The served page must make zero requests outside 127.0.0.1: no external
    URLs may appear in any fetch/src/href position. Comments may cite URLs."""
    offenders = []
    for path in sorted(glob.glob(f"{STATIC}/*")):
        text = open(path, encoding="utf-8").read()
        # strip JS/CSS comments before scanning
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"(?m)^\s*//.*$", "", text)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        for m in re.finditer(r"https?://[^\s\"'<>)]+", text):
            if "127.0.0.1" not in m.group(0) and "localhost" not in m.group(0):
                offenders.append(f"{path}: {m.group(0)}")
    assert offenders == [], offenders


def test_without_graphviz_serve_degrades_honestly(monkeypatch):
    import graphspec.serve as serve_mod
    monkeypatch.setattr(serve_mod, "graphviz_available", lambda: False)
    yaml_text = open(REFERENCE, encoding="utf-8").read()
    r = render_payload(yaml_text, REFERENCE)
    assert r["format"] == "dot" and r["dot"]
    v = validate_payload(yaml_text, REFERENCE)
    assert v["valid"] is True and v["source_map"]


@pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz not installed")
def test_serve_svg_byte_identical_to_cli_svg():
    """Golden check: /render SVG == `graphspec render --format svg` for the
    reference example under the same Graphviz version (one renderer)."""
    yaml_text = open(REFERENCE, encoding="utf-8").read()
    served = render_payload(yaml_text, REFERENCE)
    assert served["format"] == "svg"
    cli = subprocess.run(
        [".venv/bin/graphspec", "render", REFERENCE, "--format", "svg"],
        capture_output=True, check=True,
    ).stdout.decode("utf-8")
    assert served["svg"] == cli


def test_extension_modules_are_not_placeholders():
    for name in ("lens.js", "traceoverlay.js", "a11y.js"):
        content = open(os.path.join(STATIC, name), encoding="utf-8").read()
        assert len(content) > 500, f"{name} still a placeholder"


def test_source_map_covers_every_element():
    yaml_text = open(REFERENCE, encoding="utf-8").read()
    payload = validate_payload(yaml_text, REFERENCE)
    g = load(REFERENCE)
    kinds = {"node": 0, "edge": 0, "state": 0}
    for e in payload["source_map"]:
        kinds[e["kind"]] += 1
    assert kinds == {"node": len(g.nodes), "edge": len(g.edges), "state": len(g.state)}
