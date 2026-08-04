from graphspec.parser import load
from graphspec.rules.e_no_terminal import e_no_terminal


def test_fires_on_broken_fixture():
    diags = e_no_terminal(load("examples/broken-e-no-terminal.yaml"))
    assert diags, "rule must fire on its fixture"
    assert all(d.rule_id == "E-NO-TERMINAL" for d in diags)
    assert all(d.severity == "error" for d in diags)
    assert all(d.line > 0 for d in diags)


def test_reference_example_clean():
    assert e_no_terminal(load("examples/software-delivery.yaml")) == []
