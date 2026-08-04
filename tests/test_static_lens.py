"""Structural checks for graphspec/static/lens.js (the data-flow lens).

This module is plain JS loaded in a browser after app.js; it has no Python
runtime to unit-test directly. These checks assert the load-bearing strings
and patterns the UI-SPEC's "data-flow lens" section requires are present,
and that the file makes no external network requests.
"""

import re

import pytest

LENS_PATH = "graphspec/static/lens.js"


@pytest.fixture(scope="module")
def source():
    with open(LENS_PATH, encoding="utf-8") as fh:
        return fh.read()


def _strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(?m)//.*$", "", text)
    return text


def test_calls_the_flow_endpoint(source):
    assert "/flow" in source


def test_uses_aria_pressed_for_chip_state(source):
    assert "aria-pressed" in source


def test_paints_with_lens_prefixed_classes(source):
    classes = re.findall(r"lens-[a-z-]+", source)
    assert classes, "no lens- prefixed class names found"
    # every painted class the UI-SPEC calls for should be represented
    for expected in ("lens-writer", "lens-reader-required", "lens-reader-optional",
                      "lens-edge-writer", "lens-unset-edge", "lens-unset-node"):
        assert expected in source, f"missing {expected}"


def test_consumes_unset_paths(source):
    assert "unset_paths" in source


def test_handles_escape_key(source):
    assert "Escape" in source
    assert "keydown" in source


def test_wrapped_in_an_iife(source):
    stripped = _strip_comments(source).strip()
    assert stripped.startswith("(function")
    assert stripped.endswith("})();")


def test_defers_to_gs_extension_api(source):
    # must ride on window.gs, never re-implement fetch/DOM plumbing app.js owns
    assert "window.gs" in source
    assert "gs.api(" in source
    assert "gs.on(" in source
    assert "gs.findSvgElement(" in source


def test_respects_the_trace_overlay(source):
    assert "overlayActive" in source


def test_no_external_network_requests(source):
    """Only 127.0.0.1/localhost URLs may appear, and only inside comments."""
    text = _strip_comments(source)
    for m in re.finditer(r"https?://[^\s\"'<>)]+", text):
        assert "127.0.0.1" in m.group(0) or "localhost" in m.group(0), (
            f"external URL found outside comments: {m.group(0)}"
        )


def test_no_bare_http_urls_anywhere_including_comments(source):
    # belt-and-suspenders: even in comments, only loopback references allowed
    for m in re.finditer(r"https?://[^\s\"'<>)]+", source):
        assert "127.0.0.1" in m.group(0) or "localhost" in m.group(0), (
            f"non-loopback URL present: {m.group(0)}"
        )


def test_not_a_placeholder(source):
    assert len(source) > 500
    assert "filled by the M5 fan-out" not in source
