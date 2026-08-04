"""Line-tracking YAML parser: ``graphspec.yaml`` -> :class:`graphspec.model.Graph`.

Built on ``yaml.compose`` so every node, edge and state field carries the
1-based line it was declared on — rule messages need ``file:line``.

The parser is deliberately lenient: structural impossibilities (unparseable
YAML, an edge without ``from``) are ``E-PARSE`` errors; semantic problems (bad
``kind``, unreachable node) are left to the validation rules; unknown keys are
``W-UNKNOWN-KEY`` warnings, because the format must stay extensible.
"""

from __future__ import annotations

import yaml

from graphspec.diagnostics import Diagnostic
from graphspec.model import Edge, Graph, Node, StateField, parse_read

TOP_KEYS = {"graphspec", "name", "entry", "terminals", "substrate", "state", "nodes", "edges", "checkpoints"}
NODE_KEYS = {
    "kind", "tools", "budget_tokens", "effects", "agent", "substrate", "model",
    "fan_out_over", "as", "concurrency", "isolation", "idempotency_key",
    "verifies", "join", "timeout", "on_timeout", "presents", "impl",
}
EDGE_KEYS = {"from", "to", "when", "max", "counter", "on_exhausted"}
STATE_KEYS = {"type", "values", "write", "read"}
CHECKPOINT_KEYS = {"after"}

_SCALAR_TAGS = {
    "tag:yaml.org,2002:int": int,
    "tag:yaml.org,2002:float": float,
}


def _plain(node):
    """Convert a composed yaml node tree into plain Python data."""
    if node is None:
        return None
    if isinstance(node, yaml.ScalarNode):
        tag = node.tag
        if tag == "tag:yaml.org,2002:null":
            return None
        if tag == "tag:yaml.org,2002:bool":
            return node.value.lower() in ("true", "yes", "on")
        if tag in _SCALAR_TAGS:
            try:
                return _SCALAR_TAGS[tag](node.value)
            except ValueError:
                return node.value
        return node.value
    if isinstance(node, yaml.SequenceNode):
        return [_plain(v) for v in node.value]
    if isinstance(node, yaml.MappingNode):
        return {_plain(k): _plain(v) for k, v in node.value}
    return None


def _line(node) -> int:
    return node.start_mark.line + 1 if node is not None else 0


def _items(mapping):
    """Yield (key, value_node, key_line) for a MappingNode; empty otherwise."""
    if not isinstance(mapping, yaml.MappingNode):
        return
    for k, v in mapping.value:
        yield _plain(k), v, _line(k)


def _str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


class _Ctx:
    def __init__(self, path: str):
        self.path = path
        self.diags: list[Diagnostic] = []

    def error(self, line: int, message: str, hint: str = "", rule_id: str = "E-PARSE"):
        self.diags.append(Diagnostic(self.path, line, rule_id, "error", message, hint))

    def warn(self, line: int, message: str, hint: str = "", rule_id: str = "W-UNKNOWN-KEY"):
        self.diags.append(Diagnostic(self.path, line, rule_id, "warning", message, hint))

    def check_keys(self, mapping, known: set[str], where: str):
        for key, _v, kline in _items(mapping):
            if key not in known:
                self.diags.append(Diagnostic(
                    self.path, kline, "W-UNKNOWN-KEY", "warning",
                    f"unknown key '{key}' in {where}",
                    "unknown keys are ignored; check for a typo or a newer format version",
                ))


def _parse_state(ctx: _Ctx, mapping) -> dict[str, StateField]:
    fields: dict[str, StateField] = {}
    for name, value_node, kline in _items(mapping):
        ctx.check_keys(value_node, STATE_KEYS, f"state field '{name}'")
        data = _plain(value_node) or {}
        if not isinstance(data, dict):
            ctx.error(kline, f"state field '{name}' must be a mapping",
                      "write e.g. {type: string, write: [a], read: [b]}")
            continue
        ftype = str(data.get("type", ""))
        values = data.get("values")
        if ftype == "enum" and not values:
            ctx.error(kline, f"enum state field '{name}' requires 'values'",
                      "list the allowed values: values: [a, b, c]")
        fields[str(name)] = StateField(
            name=str(name),
            type=ftype,
            line=kline,
            values=[str(v) for v in values] if isinstance(values, list) else None,
            write=_str_list(data.get("write")),
            read=[parse_read(str(r)) for r in _str_list(data.get("read"))],
        )
    return fields


def _parse_nodes(ctx: _Ctx, mapping) -> dict[str, Node]:
    nodes: dict[str, Node] = {}
    for name, value_node, kline in _items(mapping):
        ctx.check_keys(value_node, NODE_KEYS, f"node '{name}'")
        data = _plain(value_node) or {}
        if not isinstance(data, dict):
            ctx.error(kline, f"node '{name}' must be a mapping", "write e.g. {kind: function, impl: x.py}")
            continue

        def _int(key):
            v = data.get(key)
            return v if isinstance(v, int) else None

        nodes[str(name)] = Node(
            name=str(name),
            kind=str(data.get("kind", "")),
            line=kline,
            raw=data,
            agent=data.get("agent"),
            model=data.get("model"),
            tools=_str_list(data.get("tools")) if data.get("tools") is not None else None,
            substrate=data.get("substrate"),
            fan_out_over=data.get("fan_out_over"),
            as_=data.get("as"),
            concurrency=_int("concurrency"),
            isolation=data.get("isolation"),
            effects=str(data.get("effects", "none")),
            idempotency_key=data.get("idempotency_key"),
            verifies=data.get("verifies"),
            join=data.get("join"),
            timeout=str(data["timeout"]) if data.get("timeout") is not None else None,
            on_timeout=data.get("on_timeout"),
            presents=_str_list(data.get("presents")) if data.get("presents") is not None else None,
            impl=data.get("impl"),
            budget_tokens=_int("budget_tokens"),
        )
    return nodes


def _parse_edges(ctx: _Ctx, sequence) -> list[Edge]:
    edges: list[Edge] = []
    if not isinstance(sequence, yaml.SequenceNode):
        if sequence is not None:
            ctx.error(_line(sequence), "'edges' must be a list", "each edge is {from: a, to: b}")
        return edges
    for item in sequence.value:
        ctx.check_keys(item, EDGE_KEYS, "edge")
        data = _plain(item) or {}
        eline = _line(item)
        if not isinstance(data, dict) or "from" not in data or "to" not in data:
            ctx.error(eline, "every edge requires 'from' and 'to'", "write {from: a, to: b}")
            continue
        max_ = data.get("max")
        edges.append(Edge(
            from_=str(data["from"]),
            to=str(data["to"]),
            line=eline,
            when=data.get("when"),
            max=max_ if isinstance(max_, int) else None,
            counter=data.get("counter"),
            on_exhausted=data.get("on_exhausted"),
        ))
    return edges


def load(path: str) -> Graph:
    """Parse *path* into a Graph. Never raises on bad input: an unparseable file
    yields an empty Graph whose ``parse_diagnostics`` carry the error."""
    ctx = _Ctx(path)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        graph = Graph(path=path)
        ctx.error(0, f"cannot read file: {exc}", "check the path; the default input is ./graphspec.yaml")
        graph.parse_diagnostics = ctx.diags
        return graph
    return loads(text, path)


def loads(text: str, path: str = "graphspec.yaml") -> Graph:
    """Parse YAML *text* (same code path as :func:`load`; ``serve`` uses this)."""
    ctx = _Ctx(path)
    graph = Graph(path=path)
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark else 0
        ctx.error(line, f"YAML does not parse: {getattr(exc, 'problem', exc)}",
                  "fix the syntax; the graph below is the last valid one")
        graph.parse_diagnostics = ctx.diags
        return graph
    if root is None:
        ctx.error(0, "file is empty", "start from an example: graphspec.yaml with 'graphspec: 1'")
        graph.parse_diagnostics = ctx.diags
        return graph
    if not isinstance(root, yaml.MappingNode):
        ctx.error(_line(root), "top level must be a mapping", "start with 'graphspec: 1'")
        graph.parse_diagnostics = ctx.diags
        return graph

    ctx.check_keys(root, TOP_KEYS, "top level")
    top = {k: (v, kl) for k, v, kl in _items(root)}

    if "graphspec" not in top:
        ctx.error(_line(root), "missing format version key 'graphspec'", "add 'graphspec: 1' at the top level")
    else:
        version = _plain(top["graphspec"][0])
        if version != 1:
            ctx.error(top["graphspec"][1], f"unsupported format version {version!r}",
                      "this tool implements 'graphspec: 1'")

    graph.name = str(_plain(top["name"][0])) if "name" in top else ""
    graph.entry = str(_plain(top["entry"][0])) if "entry" in top else ""
    graph.terminals = _str_list(_plain(top["terminals"][0])) if "terminals" in top else []
    graph.substrate = _plain(top["substrate"][0]) if "substrate" in top else None
    if not graph.entry:
        ctx.error(_line(root), "missing 'entry'", "name the node where every run starts")
    if not graph.terminals:
        ctx.error(_line(root), "missing 'terminals'", "list the nodes where a run may end")

    if "state" in top:
        graph.state = _parse_state(ctx, top["state"][0])
    if "nodes" in top:
        graph.nodes = _parse_nodes(ctx, top["nodes"][0])
    else:
        ctx.error(_line(root), "missing 'nodes'", "declare at least the entry node")
    if "edges" in top:
        graph.edges = _parse_edges(ctx, top["edges"][0])
    if "checkpoints" in top:
        ctx.check_keys(top["checkpoints"][0], CHECKPOINT_KEYS, "checkpoints")
        data = _plain(top["checkpoints"][0]) or {}
        if isinstance(data, dict):
            graph.checkpoints_after = _str_list(data.get("after"))

    graph.parse_diagnostics = ctx.diags
    return graph
