from graphspec.parser import load
from graphspec.rules.e_when_unset import e_when_unset


def test_fires_on_broken_fixture():
    diags = e_when_unset(load("examples/broken-e-when-unset.yaml"))
    assert diags, "rule must fire on its fixture"
    assert all(d.rule_id in ("E-WHEN-UNSET", "E-PARSE") for d in diags)
    assert all(d.severity == "error" for d in diags)
    assert all(d.line > 0 for d in diags)
    assert any(d.rule_id == "E-WHEN-UNSET" for d in diags)


def test_reference_example_clean():
    assert e_when_unset(load("examples/software-delivery.yaml")) == []
