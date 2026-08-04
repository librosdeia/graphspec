from graphspec.parser import load
from graphspec.rules.e_cycle_cap import e_cycle_cap


def test_fires_on_broken_fixture():
    diags = e_cycle_cap(load("examples/broken-e-cycle-cap.yaml"))
    assert diags, "rule must fire on its fixture"
    assert all(d.rule_id == "E-CYCLE-CAP" for d in diags)
    assert all(d.severity == "error" for d in diags)
    assert all(d.line > 0 for d in diags)


def test_reference_example_clean():
    assert e_cycle_cap(load("examples/software-delivery.yaml")) == []
