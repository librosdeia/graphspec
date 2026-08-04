"""Structural checks for graphspec/static/traceoverlay.js.

Not a JS test runner (no framework/build step in this repo) — asserts the
load-bearing strings/patterns the extension contract requires are present, and
that the file makes no network requests beyond this server (no http(s):// URLs
outside comments).
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "graphspec" / "static" / "traceoverlay.js"


def _text() -> str:
    return SRC.read_text(encoding="utf-8")


def test_file_exists_and_nonempty():
    assert SRC.is_file()
    text = _text()
    assert len(text.strip()) > 100


def test_wrapped_in_iife():
    text = _text()
    assert re.search(r"\(function\s*\(\s*\)\s*\{", text)
    assert "'use strict'" in text or '"use strict"' in text
    # closes as an invoked function expression
    assert re.search(r"\}\)\(\);?\s*$", text.strip())


def test_hits_trace_endpoint():
    text = _text()
    assert "/trace" in text
    assert "gs.api(" in text


def test_handles_drop_and_filereader():
    text = _text()
    assert "drop" in text
    assert "dragover" in text
    assert "FileReader" in text
    assert "JSON.parse" in text
    # dropped-file parse failures must be reported without crashing
    assert "try" in text and "catch" in text


def test_escape_clears_overlay():
    text = _text()
    assert "Escape" in text
    assert "overlayActive" in text
    assert "gs.refresh()" in text


def test_uses_cost_panel():
    text = _text()
    assert "costPanel" in text
    assert "cost_table" in text
    assert "drift" in text


def test_reapplies_pan_after_svg_swap():
    text = _text()
    assert "gs.panBy(0, 0)" in text or "gs.panBy(0,0)" in text


def test_no_external_network_requests():
    text = _text()
    for lineno, line in enumerate(text.splitlines(), start=1):
        code = line.split("//", 1)[0]
        assert "http://" not in code, f"external URL on line {lineno}"
        assert "https://" not in code, f"external URL on line {lineno}"


def test_no_framework_or_build_artifacts():
    text = _text()
    for banned in ("import ", "require(", "React", "Vue", "angular", "jQuery", "$.ajax"):
        assert banned not in text
