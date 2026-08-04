from graphspec.parser import load
from graphspec.rules.e_fanout import e_fanout


def test_fires_on_broken_fixture():
    diags = e_fanout(load("examples/broken-e-fanout.yaml"))
    assert diags, "rule must fire on its fixture"
    assert all(d.rule_id == "E-FANOUT" for d in diags)
    assert all(d.severity == "error" for d in diags)
    assert all(d.line > 0 for d in diags)
    assert len(diags) >= 2


def test_reference_example_clean():
    assert e_fanout(load("examples/software-delivery.yaml")) == []
