from graphspec.parser import load
from graphspec.rules.e_unreachable import e_unreachable


def test_fires_on_broken_fixture():
    diags = e_unreachable(load("examples/broken-e-unreachable.yaml"))
    assert diags, "rule must fire on its fixture"
    assert all(d.rule_id == "E-UNREACHABLE" for d in diags)
    assert all(d.severity == "error" for d in diags)
    assert all(d.line > 0 for d in diags)


def test_reference_example_clean():
    assert e_unreachable(load("examples/software-delivery.yaml")) == []
