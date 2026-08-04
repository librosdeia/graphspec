"""scaffold: state-binding schemas, correlation labels, contracts, idempotency."""

import hashlib
import os
import pathlib
import shutil

import pytest

from graphspec.parser import load
from graphspec.scaffold import (
    agent_md, hooks_fragment, run, state_schema, when_to_js, workflow_script,
)

REFERENCE = "examples/software-delivery.yaml"


# ------------------------------------------------------------------- schemas

def test_state_schema_derived_from_writes_with_enum_values():
    g = load(REFERENCE)
    schema = state_schema(g, "triage")
    assert schema == {
        "type": "object",
        "required": ["category", "issue_id"],
        "properties": {
            "category": {"type": "string", "enum": ["feature", "bugfix", "drop"]},
            "issue_id": {"type": "string"},
        },
    }


def test_no_writes_means_no_schema():
    g = load(REFERENCE)
    assert state_schema(g, "implement") is None  # fan-out nodes must not write
    assert state_schema(g, "dropped") is None


# ------------------------------------------------------------------ when->js

@pytest.mark.parametrize("src,js", [
    ("category == 'feature'", "state.category === 'feature'"),
    ("a < 3 && b != 'x'", "(state.a < 3 && state.b !== 'x')"),
    ("!done || tries >= 2", "(!(state.done) || state.tries >= 2)"),
])
def test_when_to_js(src, js):
    assert when_to_js(src) == js


# ------------------------------------------------------------------ agent md

def test_agent_md_frontmatter_and_contract():
    g = load(REFERENCE)
    md = agent_md(g, g.nodes["implement"])
    head = md.split("---")[1]
    assert "name: implementer" in head
    assert "model: claude-sonnet-5" in head
    md_verify = agent_md(g, g.nodes["verify"])
    assert "model: claude-opus-5" in md_verify
    # optional read marked
    assert "`spec` (ref) *(optional" in md
    # fan-out contract stated
    assert "fans out over `branches`" in md
    assert "{issue_id}-{branch}" in md
    # correlation label documented
    assert "graphspec:implement" in md


# ------------------------------------------------------------------ workflow

def test_workflow_script_carries_labels_schemas_and_caps():
    g = load(REFERENCE)
    js = workflow_script(g)
    # meta is first statement; generated header comment above it
    assert "export const meta = {" in js
    # correlation labels on every generated unit
    for node in ("triage", "spec", "fanout", "implement", "verify", "merge"):
        assert f"label: 'graphspec:{node}'" in js
    # structured-output schema injected for writing nodes only
    assert "schema: SCHEMAS.triage" in js
    assert "SCHEMAS.implement" not in js
    # counters initialized at run start
    assert "const state = { attempts: 0, revisions: 0 }" in js
    # capped edge: increment + exhaustion routing
    assert "state.attempts += 1" in js
    assert "if (state.attempts > 3)" in js
    # fan-out chunked by concurrency with worktree isolation
    assert "i += 3" in js
    assert "isolation: 'worktree'" in js
    # guards translated
    assert "state.category === 'feature'" in js
    # human node returns pending state, clearly marked
    assert "return { pending: 'gate'" in js
    # subagent nodes use their declared agent
    assert "agentType: 'spec-writer'" in js


def test_workflow_script_deterministic():
    g = load(REFERENCE)
    assert workflow_script(g) == workflow_script(load(REFERENCE))


def test_render_only_substrates_pass_through_with_comment():
    g = load("examples/research-publishing.yaml")
    js = workflow_script(g)
    assert "render-only in graphspec 1" in js


# ----------------------------------------------------------------- full runs

def _tree_hash(root: str) -> dict[str, str]:
    out = {}
    for base, _dirs, names in os.walk(root):
        for n in names:
            p = os.path.join(base, n)
            out[os.path.relpath(p, root)] = hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
    return out


def test_scaffold_run_and_idempotency(tmp_path, capsys):
    out = tmp_path / "proj"
    assert run(REFERENCE, out=str(out)) == 0
    first = _tree_hash(str(out))
    assert ".claude/agents/implementer.md" in first
    assert ".claude/agents/spec-writer.md" in first
    assert ".claude/agents/verifier.md" in first
    assert ".claude/workflows/software-delivery.js" in first
    assert ".claude/graphspec/hooks-fragment.json" in first
    capsys.readouterr()
    # second run: identical tree, everything skipped
    assert run(REFERENCE, out=str(out)) == 0
    assert _tree_hash(str(out)) == first
    assert "skip" in capsys.readouterr().out
    # --force rewrites but content is identical (deterministic generator)
    assert run(REFERENCE, out=str(out), force=True) == 0
    assert _tree_hash(str(out)) == first


def test_scaffold_warns_on_render_only_substrates(tmp_path, capsys):
    assert run("examples/research-publishing.yaml", out=str(tmp_path / "o")) == 0
    err = capsys.readouterr().err
    assert "render-only" in err
    assert "scheduled" in err or "channel" in err


def test_scaffold_creates_missing_impl_stubs(tmp_path, capsys):
    yaml_dir = tmp_path / "g"
    yaml_dir.mkdir()
    (yaml_dir / "graphspec.yaml").write_text(
        "graphspec: 1\nname: stubby\nentry: a\nterminals: [z]\n"
        "state:\n  done: {type: bool, write: [a]}\n"
        "nodes:\n  a: {kind: function, impl: scripts/do_it.py}\n  z: {kind: terminal}\n"
        "edges:\n  - {from: a, to: z}\n",
        encoding="utf-8",
    )
    # a missing impl is an E-KIND error, but stubbing it is scaffold's job:
    # tolerated, stub written, and a re-run then validates clean
    assert run(str(yaml_dir / "graphspec.yaml"), out=str(tmp_path / "o")) == 0
    stub = yaml_dir / "scripts" / "do_it.py"
    assert stub.is_file()
    assert "generated stub for node 'a'" in stub.read_text(encoding="utf-8")
    from graphspec.validate import run_rules
    assert [d for d in run_rules(load(str(yaml_dir / "graphspec.yaml")))
            if d.severity == "error"] == []


def test_scaffold_refuses_invalid_graph(tmp_path, capsys):
    p = tmp_path / "bad.yaml"
    p.write_text(
        "graphspec: 1\nname: bad\nentry: a\nterminals: [z]\n"
        "nodes:\n  a: {kind: llm}\n  z: {kind: terminal}\n"
        "edges:\n  - {from: a, to: ghost}\n",
        encoding="utf-8",
    )
    assert run(str(p), out=str(tmp_path / "o")) == 1
    assert "E-EDGE-ENDS" in capsys.readouterr().err


def test_hooks_fragment_lists_deterministic_edges():
    import json
    g = load(REFERENCE)
    frag = json.loads(hooks_fragment(g))
    assert {"from": "spec", "to": "fanout"} in frag["deterministic_edges"]
    assert {"from": "fanout", "to": "implement"} in frag["deterministic_edges"]
    assert "PostToolUse" in frag["hooks"]
