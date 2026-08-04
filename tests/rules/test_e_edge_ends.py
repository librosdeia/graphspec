from graphspec.parser import load
from graphspec.rules.e_edge_ends import e_edge_ends


def test_fires_on_broken_fixture():
    diags = e_edge_ends(load("examples/broken-e-edge-ends.yaml"))
    assert diags, "rule must fire on its fixture"
    assert all(d.rule_id == "E-EDGE-ENDS" for d in diags)
    assert all(d.severity == "error" for d in diags)
    assert all(d.line > 0 for d in diags)


def test_reference_example_clean():
    assert e_edge_ends(load("examples/software-delivery.yaml")) == []
