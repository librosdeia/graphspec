from graphspec.parser import load
from graphspec.rules.e_human import e_human


def test_fires_on_broken_fixture():
    diags = e_human(load("examples/broken-e-human.yaml"))
    assert diags, "rule must fire on its fixture"
    assert all(d.rule_id == "E-HUMAN" for d in diags)
    assert all(d.severity == "error" for d in diags)
    assert all(d.line > 0 for d in diags)
    assert len(diags) == 2
    messages = {d.message for d in diags}
    assert any("without a timeout" in m for m in messages)
    assert any("without on_timeout" in m for m in messages)


def test_reference_example_clean():
    assert e_human(load("examples/software-delivery.yaml")) == []
