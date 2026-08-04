"""Structural checks for graphspec/static/a11y.js.

a11y.js is a plain-JS extension module loaded after app.js in the browser —
nothing here executes JavaScript. These tests read the source text and assert
the load-bearing patterns the UI-SPEC's "Accessibility & keyboard" section
requires are present, and that the file makes no network requests of its own
(zero external URLs, matching the PRD's local-first constraint).
"""

import pathlib
import re

import pytest

A11Y_JS = pathlib.Path(__file__).resolve().parent.parent / "graphspec" / "static" / "a11y.js"


@pytest.fixture(scope="module")
def source():
    return A11Y_JS.read_text(encoding="utf-8")


def test_file_exists_and_nonempty():
    assert A11Y_JS.is_file()
    assert A11Y_JS.stat().st_size > 0


def test_wrapped_in_iife(source):
    # No global leakage: the whole module body runs inside a self-invoking
    # function expression, `(function () { ... })();`.
    assert re.search(r"\(function\s*\(\s*\)\s*\{", source)
    assert re.search(r"\}\)\s*\(\s*\)\s*;\s*$", source.rstrip())


def test_uses_strict_mode(source):
    assert "'use strict'" in source or '"use strict"' in source


@pytest.mark.parametrize("needle", [
    "F8",              # problem-cycling key
    "aria-keyshortcuts",
    "panBy",           # canvas pan via the gs API
    "tabindex",        # problem-list items made keyboard-focusable
    "visually-hidden",  # keyboard-help region CSS class (sr-only pattern)
])
def test_contains_load_bearing_string(source, needle):
    assert needle in source, f"expected {needle!r} in a11y.js"


def test_full_keymap_present(source):
    # Every control in the UI-SPEC keymap table must be wired up.
    assert "Shift" in source and "F8" in source
    assert "toggleExport" in source
    assert "toggleProblems" in source
    assert "zoom" in source
    assert "fit" in source
    assert "Escape" in source


def test_gotoProblem_used_for_f8(source):
    assert "gotoProblem" in source


def test_role_img_and_aria_label_on_render(source):
    assert 'setAttribute(\'role\', \'img\')' in source or 'setAttribute("role", "img")' in source
    assert "aria-label" in source
    assert "graph " in source  # the "graph <name>" label prefix


def test_problem_list_items_get_role_button(source):
    assert "role', 'button'" in source or 'role", "button"' in source


def test_aria_controls_on_problems_toggle(source):
    assert "aria-controls" in source
    assert "problemlist" in source


def test_editor_typing_not_intercepted_for_arrow_pan(source):
    # The editor textarea must be excluded from the canvas pan/zoom branch —
    # look for the documented early-return guard against gs.editor.
    assert "gs.editor" in source
    assert re.search(r"if\s*\(e\.target\s*===\s*gs\.editor\)\s*return", source)


def test_no_external_network_requests(source):
    """No http(s):// URL anywhere — this is a local-only, zero-network module.

    Even a URL sitting only in a comment would fail the acceptance check's
    request-log style audit if ever copy-pasted into an active string, so we
    simply require none exist anywhere in the file.
    """
    assert not re.search(r"https?://", source), (
        "a11y.js must not contain any http(s):// URL (no external requests, "
        "no CDN links, not even in comments)"
    )
    for banned in ("fetch(", "XMLHttpRequest", "WebSocket", "importScripts", "<script"):
        assert banned not in source, f"unexpected network/script primitive: {banned!r}"


def test_uses_gs_api_only_no_raw_fetch(source):
    # The module must talk to the editor exclusively through window.gs; it
    # should never call the raw fetch API itself (gs.api already wraps it).
    assert "window.gs" in source or "gs.on" in source
