from graphspec.parser import load, loads
from graphspec.rules.w_self_read import w_self_read
from graphspec.rules.w_counter_write import w_counter_write
from graphspec.rules.w_advisory import advisory_warnings


SELF_READ_YAML = """
graphspec: 1
name: self-read-demo
entry: triage
terminals: [done]

state:
  category: {type: string, write: [triage], read: [triage]}

nodes:
  triage: {kind: function, impl: scripts/triage.py, effects: none}
  done:   {kind: terminal}

edges:
  - {from: triage, to: done}
"""


COUNTER_WRITE_YAML = """
graphspec: 1
name: counter-write-demo
entry: work
terminals: [done]

state:
  attempts: {type: number, write: [work]}

nodes:
  work: {kind: function, impl: scripts/work.py, effects: none}
  done: {kind: terminal}

edges:
  - {from: work, to: work, when: "attempts < 3", max: 3, counter: attempts, on_exhausted: done}
  - {from: work, to: done, when: "attempts >= 3"}
"""


def test_self_read_fires():
    diags = w_self_read(loads(SELF_READ_YAML, path="self-read-demo.yaml"))
    assert diags, "rule must fire on the self-read fixture"
    assert all(d.rule_id == "W-SELF-READ" for d in diags)
    assert all(d.severity == "warning" for d in diags)
    assert all(d.line > 0 for d in diags)
    assert "triage" in diags[0].message
    assert "category" in diags[0].message


def test_self_read_clean_when_no_self_read():
    graph = loads(
        """
graphspec: 1
name: clean-demo
entry: a
terminals: [b]

state:
  x: {type: string, write: [a], read: [b]}

nodes:
  a: {kind: function, impl: scripts/a.py, effects: none}
  b: {kind: terminal}

edges:
  - {from: a, to: b}
""",
        path="clean-demo.yaml",
    )
    assert w_self_read(graph) == []


def test_counter_write_fires():
    diags = w_counter_write(loads(COUNTER_WRITE_YAML, path="counter-write-demo.yaml"))
    assert diags, "rule must fire on the counter-write fixture"
    assert all(d.rule_id == "W-COUNTER-WRITE" for d in diags)
    assert all(d.severity == "warning" for d in diags)
    assert all(d.line > 0 for d in diags)
    assert "attempts" in diags[0].message


def test_counter_write_clean_when_counter_not_written_by_node():
    graph = loads(
        """
graphspec: 1
name: clean-counter-demo
entry: work
terminals: [done]

state:
  attempts: {type: number}

nodes:
  work: {kind: function, impl: scripts/work.py, effects: none}
  done: {kind: terminal}

edges:
  - {from: work, to: work, when: "attempts < 3", max: 3, counter: attempts, on_exhausted: done}
  - {from: work, to: done, when: "attempts >= 3"}
""",
        path="clean-counter-demo.yaml",
    )
    assert w_counter_write(graph) == []


def test_reference_example_has_no_self_read_or_counter_write_warnings():
    graph = load("examples/software-delivery.yaml")
    assert w_self_read(graph) == []
    assert w_counter_write(graph) == []


def test_advisory_warnings_non_claude_target_is_empty():
    graph = load("examples/software-delivery.yaml")
    assert advisory_warnings(graph, "python") == []
    assert advisory_warnings(graph, None) == []


def test_advisory_warnings_for_claude_target():
    graph = load("examples/software-delivery.yaml")
    diags = advisory_warnings(graph, "claude")
    assert diags, "advisory_warnings must fire for --target claude on this graph"
    assert all(d.rule_id == "W-ADVISORY" for d in diags)
    assert all(d.severity == "warning" for d in diags)

    messages = " ".join(d.message for d in diags)
    assert "budget_tokens" in messages
    assert "triage" in messages
    assert "gate" in messages
    assert "checkpoint" in messages.lower()
