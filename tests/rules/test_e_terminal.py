from graphspec.parser import load
from graphspec.rules.e_terminal import e_terminal


def test_fires_on_broken_fixture():
    diags = e_terminal(load("examples/broken-e-terminal.yaml"))
    assert diags, "rule must fire on its fixture"
    assert all(d.rule_id == "E-TERMINAL" for d in diags)
    assert all(d.severity == "error" for d in diags)
    assert all(d.line > 0 for d in diags)
    assert len(diags) >= 2


def test_reference_example_clean():
    assert e_terminal(load("examples/software-delivery.yaml")) == []
