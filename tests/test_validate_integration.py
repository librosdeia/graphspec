"""All rules together: the reference example stays clean, every fixture fires its rule."""

import glob
import os
import re

import pytest

from graphspec.parser import load, loads
from graphspec.validate import run, run_rules

REFERENCE = "examples/software-delivery.yaml"

EXPECTED_RULES = {
    "E-EDGE-ENDS", "E-UNREACHABLE", "E-NO-TERMINAL", "E-TERMINAL", "E-KIND",
    "E-READ-UNSET", "E-WHEN-UNSET", "E-VERIFIER", "E-FANOUT", "E-CYCLE-CAP",
    "E-EFFECTS", "E-HUMAN",
}


def test_all_error_rules_are_registered():
    import graphspec.rules as rules_pkg
    assert EXPECTED_RULES <= set(rules_pkg.ALL_RULES), (
        "missing rules: " + ", ".join(sorted(EXPECTED_RULES - set(rules_pkg.ALL_RULES))))
    assert {"W-SELF-READ", "W-COUNTER-WRITE"} <= set(rules_pkg.ALL_RULES)


def test_reference_example_is_fully_clean():
    assert run_rules(load(REFERENCE)) == []


def test_reference_example_clean_even_strict(capsys):
    assert run(REFERENCE, strict=True) == 0


def test_target_claude_warns_advisory_but_exits_zero(capsys):
    assert run(REFERENCE, target="claude") == 0
    out = capsys.readouterr().out
    assert "[W-ADVISORY]" in out
    assert "budget_tokens" in out


def _fixture_rule_id(path: str) -> str:
    return os.path.basename(path)[len("broken-"):-len(".yaml")].upper()


def test_one_fixture_exists_per_error_rule():
    found = {_fixture_rule_id(p) for p in glob.glob("examples/broken-e-*.yaml")}
    assert found == EXPECTED_RULES


@pytest.mark.parametrize("path", sorted(glob.glob("examples/broken-e-*.yaml")))
def test_each_fixture_fires_its_exact_rule(path):
    rule_id = _fixture_rule_id(path)
    diags = run_rules(load(path))
    fired = {d.rule_id for d in diags if d.severity == "error"}
    assert rule_id in fired, f"{path} must fire {rule_id}, fired: {sorted(fired)}"
    for d in diags:
        assert re.match(r"^[EW]-[A-Z-]+$", d.rule_id)
        assert d.line >= 0


def test_strict_promotes_warnings(tmp_path):
    p = tmp_path / "warn.yaml"
    p.write_text(
        "graphspec: 1\nname: w\nentry: a\nterminals: [b]\nfrobnicate: 1\n"
        "nodes:\n  a: {kind: llm}\n  b: {kind: terminal}\n"
        "edges:\n  - {from: a, to: b}\n",
        encoding="utf-8",
    )
    assert run(str(p), strict=False) == 0
    assert run(str(p), strict=True) == 1


def test_diagnostics_print_file_line_rule(capsys, tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        "graphspec: 1\nname: b\nentry: a\nterminals: [z]\n"
        "nodes:\n  a: {kind: llm}\n  z: {kind: terminal}\n"
        "edges:\n  - {from: a, to: ghost}\n",
        encoding="utf-8",
    )
    assert run(str(p)) == 1
    out = capsys.readouterr().out
    assert re.search(rf"{re.escape(str(p))}:\d+: \[E-", out)
    assert "hint:" in out
