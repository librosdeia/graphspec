from graphspec.parser import load
from graphspec.rules.e_verifier import e_verifier


def test_fires_on_broken_fixture():
    diags = e_verifier(load("examples/broken-e-verifier.yaml"))
    assert diags, "rule must fire on its fixture"
    assert all(d.rule_id == "E-VERIFIER" for d in diags)
    assert all(d.severity == "error" for d in diags)
    assert all(d.line > 0 for d in diags)


def test_reference_example_clean():
    assert e_verifier(load("examples/software-delivery.yaml")) == []
