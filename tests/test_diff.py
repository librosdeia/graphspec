"""`graphspec diff` — semantic comparison of two parsed graphs.

Each change class is exercised in isolation with small tmp YAML pairs, per
the PRD's test list. The reference example is used for the identical case.
"""

from __future__ import annotations

from graphspec.diff import Change, compare, format_markdown, format_text, run
from graphspec.parser import load

REFERENCE = "examples/software-delivery.yaml"

BASE = """\
graphspec: 1
name: sample
entry: a
terminals: [c]

state:
  x: {type: string, write: [a], read: [b]}

nodes:
  a: {kind: llm, model: claude-sonnet-5}
  b: {kind: function, impl: scripts/b.py}
  c: {kind: terminal}

edges:
  - {from: a, to: b, when: "x == 'go'"}
  - {from: b, to: c}
"""


def _write(tmp_path, name: str, text: str) -> str:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# --- identical files -------------------------------------------------------


def test_identical_files_exit_0_and_empty_stdout(capsys):
    rc = run(REFERENCE, REFERENCE)
    out, err = capsys.readouterr()
    assert rc == 0
    assert out == ""
    assert err == ""


def test_identical_files_compare_returns_no_changes():
    g1 = load(REFERENCE)
    g2 = load(REFERENCE)
    assert compare(g1, g2) == []


# --- node added / removed / changed ----------------------------------------


def test_node_added(tmp_path):
    old = _write(tmp_path, "old.yaml", BASE)
    new = _write(tmp_path, "new.yaml", BASE.replace(
        "  c: {kind: terminal}\n",
        "  c: {kind: terminal}\n  d: {kind: terminal}\n",
    ))
    changes = compare(load(old), load(new))
    added = [c for c in changes if c.kind == "node" and c.action == "added"]
    assert added == [Change("node", "added", "d")]


def test_node_removed(tmp_path):
    old = _write(tmp_path, "old.yaml", BASE.replace(
        "  c: {kind: terminal}\n",
        "  c: {kind: terminal}\n  d: {kind: terminal}\n",
    ))
    new = _write(tmp_path, "new.yaml", BASE)
    changes = compare(load(old), load(new))
    removed = [c for c in changes if c.kind == "node" and c.action == "removed"]
    assert removed == [Change("node", "removed", "d")]


def test_node_changed_model(tmp_path):
    old = _write(tmp_path, "old.yaml", BASE)
    new = _write(tmp_path, "new.yaml", BASE.replace(
        "model: claude-sonnet-5", "model: claude-opus-5",
    ))
    changes = compare(load(old), load(new))
    node_changed = [c for c in changes if c.kind == "node" and c.action == "changed"]
    assert node_changed == [
        Change("node", "changed", "a", ["model: 'claude-sonnet-5' → 'claude-opus-5'"])
    ]


# --- edges: added, guard changed, cap changed -------------------------------


def test_edge_added(tmp_path):
    old = _write(tmp_path, "old.yaml", BASE)
    new = _write(tmp_path, "new.yaml", BASE.replace(
        "  - {from: b, to: c}\n",
        "  - {from: b, to: c}\n  - {from: a, to: c}\n",
    ))
    changes = compare(load(old), load(new))
    added = [c for c in changes if c.kind == "edge" and c.action == "added"]
    assert added == [Change("edge", "added", "a → c")]


def test_edge_guard_when_changed(tmp_path):
    old = _write(tmp_path, "old.yaml", BASE)
    new = _write(tmp_path, "new.yaml", BASE.replace(
        'when: "x == \'go\'"', 'when: "x == \'stop\'"',
    ))
    changes = compare(load(old), load(new))
    edge_changed = [c for c in changes if c.kind == "edge" and c.action == "changed"]
    old_when, new_when = "x == 'go'", "x == 'stop'"
    assert edge_changed == [
        Change("edge", "changed", "a → b", [f"when: '{old_when}' → '{new_when}'"])
    ]


def test_edge_cap_max_changed(tmp_path):
    capped_old = BASE.replace(
        "  - {from: b, to: c}\n",
        "  - {from: b, to: c, when: \"x == 'go'\", max: 3, counter: n, on_exhausted: c}\n",
    ).replace("  x: {type: string, write: [a], read: [b]}\n",
              "  x: {type: string, write: [a], read: [b]}\n  n: {type: number}\n")
    capped_new = capped_old.replace("max: 3", "max: 5")
    old = _write(tmp_path, "old.yaml", capped_old)
    new = _write(tmp_path, "new.yaml", capped_new)
    changes = compare(load(old), load(new))
    edge_changed = [c for c in changes if c.kind == "edge" and c.action == "changed"]
    assert edge_changed == [Change("edge", "changed", "b → c", ["max: 3 → 5"])]


def test_edge_surplus_occurrence_is_added_not_changed(tmp_path):
    """Two edges sharing a (from, to) pair: extras are added/removed, not changed."""
    old = _write(tmp_path, "old.yaml", BASE)
    two_edges = BASE.replace(
        '  - {from: a, to: b, when: "x == \'go\'"}\n',
        '  - {from: a, to: b, when: "x == \'go\'"}\n'
        '  - {from: a, to: b, when: "x == \'retry\'"}\n',
    )
    new = _write(tmp_path, "new.yaml", two_edges)
    changes = compare(load(old), load(new))
    edge_changes = [c for c in changes if c.kind == "edge"]
    assert edge_changes == [Change("edge", "added", "a → b")]


# --- state: added, type changed, read optionality changed ------------------


def test_state_field_added(tmp_path):
    old = _write(tmp_path, "old.yaml", BASE)
    new = _write(tmp_path, "new.yaml", BASE.replace(
        "  x: {type: string, write: [a], read: [b]}\n",
        "  x: {type: string, write: [a], read: [b]}\n  y: {type: number}\n",
    ))
    changes = compare(load(old), load(new))
    added = [c for c in changes if c.kind == "state" and c.action == "added"]
    assert added == [Change("state", "added", "y")]


def test_state_type_changed(tmp_path):
    old = _write(tmp_path, "old.yaml", BASE)
    new = _write(tmp_path, "new.yaml", BASE.replace(
        "x: {type: string, write: [a], read: [b]}",
        "x: {type: number, write: [a], read: [b]}",
    ))
    changes = compare(load(old), load(new))
    state_changed = [c for c in changes if c.kind == "state" and c.action == "changed"]
    assert state_changed == [
        Change("state", "changed", "x", ["type: 'string' → 'number'"])
    ]


def test_state_read_optionality_changed(tmp_path):
    old = _write(tmp_path, "old.yaml", BASE)
    new = _write(tmp_path, "new.yaml", BASE.replace(
        "x: {type: string, write: [a], read: [b]}",
        "x: {type: string, write: [a], read: ['b?']}",
    ))
    changes = compare(load(old), load(new))
    state_changed = [c for c in changes if c.kind == "state" and c.action == "changed"]
    assert state_changed == [
        Change("state", "changed", "x", ["read: ['b'] → ['b?']"])
    ]


# --- text / markdown formatting ---------------------------------------------


def test_format_text_empty_when_no_changes():
    assert format_text([]) == ""


def test_format_text_groups_kind_action_and_details():
    changes = [
        Change("node", "added", "verify"),
        Change("edge", "changed", "verify → gate", ["when: 'x' → 'y'"]),
    ]
    text = format_text(changes)
    assert text == (
        "node added: verify\n"
        "edge changed: verify → gate\n"
        "    when: 'x' → 'y'"
    )


def test_format_markdown_empty_when_no_changes():
    assert format_markdown([]) == ""


def test_format_markdown_has_header_bullets_and_backticks():
    changes = [
        Change("node", "added", "verify"),
        Change("edge", "changed", "verify → gate", ["when: 'x' → 'y'"]),
    ]
    md = format_markdown(changes)
    assert md.startswith("### graphspec diff")
    assert "**Nodes added**" in md
    assert "**Edges changed**" in md
    assert "- `verify`" in md
    assert "- `verify → gate`" in md
    assert "`when`: `'x'` → `'y'`" in md


# --- run(): exit codes, stderr on parse error -------------------------------


def test_run_returns_1_and_prints_text_when_graphs_differ(tmp_path, capsys):
    old = _write(tmp_path, "old.yaml", BASE)
    new = _write(tmp_path, "new.yaml", BASE.replace(
        "model: claude-sonnet-5", "model: claude-opus-5",
    ))
    rc = run(old, new)
    out, err = capsys.readouterr()
    assert rc == 1
    assert err == ""
    assert "node changed: a" in out
    assert "model: 'claude-sonnet-5' → 'claude-opus-5'" in out


def test_run_markdown_format(tmp_path, capsys):
    old = _write(tmp_path, "old.yaml", BASE)
    new = _write(tmp_path, "new.yaml", BASE.replace(
        "model: claude-sonnet-5", "model: claude-opus-5",
    ))
    rc = run(old, new, fmt="markdown")
    out, _err = capsys.readouterr()
    assert rc == 1
    assert out.startswith("### graphspec diff")
    assert "`model`" in out


def test_run_parse_error_prints_stderr_and_returns_2(tmp_path, capsys):
    old = _write(tmp_path, "old.yaml", BASE)
    bad = _write(tmp_path, "bad.yaml", "graphspec: 1\nentry: a\n")  # missing 'nodes'
    rc = run(old, bad)
    out, err = capsys.readouterr()
    assert rc == 2
    assert out == ""
    assert err.strip() != ""
    assert "[E-PARSE]" in err


# --- determinism -------------------------------------------------------------


def test_determinism_two_runs_are_byte_identical(tmp_path, capsys):
    old = _write(tmp_path, "old.yaml", BASE)
    new = _write(tmp_path, "new.yaml", BASE.replace(
        "model: claude-sonnet-5", "model: claude-opus-5",
    ))
    run(old, new)
    first, _ = capsys.readouterr()
    run(old, new)
    second, _ = capsys.readouterr()
    assert first == second

    md1 = format_markdown(compare(load(old), load(new)))
    md2 = format_markdown(compare(load(old), load(new)))
    assert md1 == md2
