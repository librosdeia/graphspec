from graphspec.parser import load
from graphspec.rules.e_read_unset import e_read_unset


def test_fires_on_broken_fixture():
    diags = e_read_unset(load("examples/broken-e-read-unset.yaml"))
    assert diags, "rule must fire on its fixture"
    assert all(d.rule_id == "E-READ-UNSET" for d in diags)
    assert all(d.severity == "error" for d in diags)
    assert all(d.line > 0 for d in diags)


def test_message_contains_witness_path_through_c():
    diags = e_read_unset(load("examples/broken-e-read-unset.yaml"))
    assert any("entry → c → d" in d.message for d in diags)


def test_reference_example_clean():
    assert e_read_unset(load("examples/software-delivery.yaml")) == []
