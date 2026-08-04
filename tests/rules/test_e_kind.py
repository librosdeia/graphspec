from graphspec.parser import load
from graphspec.rules.e_kind import e_kind


def test_fires_on_broken_fixture():
    diags = e_kind(load("examples/broken-e-kind.yaml"))
    assert diags, "rule must fire on its fixture"
    assert all(d.rule_id == "E-KIND" for d in diags)
    assert all(d.severity == "error" for d in diags)
    assert all(d.line > 0 for d in diags)
    assert len(diags) >= 2


def test_reference_example_clean():
    assert e_kind(load("examples/software-delivery.yaml")) == []
