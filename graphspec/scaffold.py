"""graphspec scaffold — generate Claude Code artifacts from the declared graph.

For ``--target claude`` it emits:
- ``.claude/agents/<agent>.md`` per ``kind: subagent`` node (frontmatter + the
  node's contract: reads with optional markers, writes, advisory fields,
  expected evidence).
- ``.claude/workflows/<graph-name>.js`` — a dynamic-workflow skeleton whose
  control flow is derived from the edges, guards, caps, fan-out and join
  policies. This is what turns the declared graph into the graph that runs.
- A structured-output schema per writing node, injected into the generated
  ``agent()`` call — the mechanism that keeps declaration and implementation
  in sync. A node with no writes gets no schema.
- Correlation labels ``graphspec:<node>`` on every generated unit (the trace
  contract).
- ``.claude/graphspec/hooks-fragment.json`` for edges that must fire
  deterministically, plus a validate-on-edit hook suggestion.
- Stub files for any ``impl:`` path that does not exist yet.

Re-running is idempotent: identical input produces identical output, and
existing files are left untouched unless ``--force``.

Enforced for this target: edges, ``when`` guards, ``fan_out_over``/``as``/
``concurrency``/``join``, ``isolation``, ``model``, ``agent``, state writes.
Advisory (documented, not generated): ``timeout``/``on_timeout`` on human
nodes, ``checkpoints``, ``budget_tokens``.
"""

from __future__ import annotations

import json
import os
import sys
from collections import deque

from graphspec.expr import parse_when
from graphspec.model import Graph, Node, RESERVED_TARGETS
from graphspec.parser import load
from graphspec.validate import run_rules

SCAFFOLD_SUBSTRATES = {"workflow", "subagent"}

_JSON_TYPES = {
    "string": "string", "number": "number", "bool": "boolean",
    "list": "array", "object": "object", "enum": "string", "ref": "string",
}


# --------------------------------------------------------------------- schemas

def state_schema(graph: Graph, node_name: str) -> dict | None:
    """Structured-output JSON Schema for the fields *node_name* writes."""
    writes = sorted(graph.writes_of(node_name))
    if not writes:
        return None
    props: dict[str, dict] = {}
    for name in writes:
        f = graph.state[name]
        prop: dict = {"type": _JSON_TYPES.get(f.type, "string")}
        if f.type == "enum" and f.values:
            prop["enum"] = list(f.values)
        if f.type == "ref":
            prop["description"] = "path to an artifact on disk (ref field)"
        props[name] = prop
    return {"type": "object", "required": writes, "properties": props}


# ------------------------------------------------------------ when -> JS guard

_JS_CMP = {"==": "===", "!=": "!==", "<": "<", "<=": "<=", ">": ">", ">=": ">="}


def when_to_js(src: str) -> str:
    """Translate a when expression to a JavaScript guard over ``state``."""

    def emit(ast) -> str:
        tag = ast[0]
        if tag == "ident":
            return f"state.{ast[1]}"
        if tag == "lit":
            v = ast[1]
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, str):
                return "'" + v.replace("'", "\\'") + "'"
            return repr(v)
        if tag == "not":
            return f"!({emit(ast[1])})"
        if tag == "cmp":
            return f"{emit(ast[2])} {_JS_CMP[ast[1]]} {emit(ast[3])}"
        if tag in ("and", "or"):
            op = "&&" if tag == "and" else "||"
            return f"({emit(ast[1])} {op} {emit(ast[2])})"
        raise ValueError(f"unknown ast node {tag!r}")

    return emit(parse_when(src))


# ------------------------------------------------------------------- agent .md

def _reads_lines(graph: Graph, node_name: str) -> list[str]:
    lines = []
    for f, r in sorted(graph.reads_of(node_name), key=lambda fr: fr[0].name):
        mark = " *(optional — tolerate it being unset)*" if r.optional else ""
        lines.append(f"- `{f.name}` ({f.type}){mark}")
    return lines


def _writes_lines(graph: Graph, node_name: str) -> list[str]:
    lines = []
    for name in sorted(graph.writes_of(node_name)):
        f = graph.state[name]
        extra = f" — one of {', '.join(f.values)}" if f.type == "enum" and f.values else ""
        lines.append(f"- `{name}` ({f.type}{extra})")
    return lines


def _advisory_lines(node: Node) -> list[str]:
    adv = []
    if node.budget_tokens is not None:
        adv.append(f"- `budget_tokens: {node.budget_tokens}` — enforce in the surrounding process")
    if node.kind == "human" and (node.timeout or node.on_timeout):
        adv.append(f"- `timeout: {node.timeout}` / `on_timeout: {node.on_timeout}` — the "
                   "generated workflow cannot wait for humans; it returns with pending state")
    return adv


def agent_md(graph: Graph, node: Node) -> str:
    """The .claude/agents file for a subagent node: frontmatter + contract."""
    fm = [f"name: {node.agent}"]
    fm.append(f"description: Node '{node.name}' of graph '{graph.name}' (generated by graphspec scaffold).")
    if node.tools:
        fm.append("tools: " + ", ".join(node.tools))
    if node.model:
        fm.append(f"model: {node.model}")
    reads = _reads_lines(graph, node.name) or ["- (none)"]
    writes = _writes_lines(graph, node.name) or ["- (none — this node returns no structured output)"]
    advisory = _advisory_lines(node) or ["- (none)"]
    fanout = ""
    if node.fan_out_over:
        fanout = (f"\nThis node fans out over `{node.fan_out_over}` — one run per item, bound as "
                  f"`{node.as_}`. Completed items must be cheap no-ops under the idempotency key "
                  f"`{node.idempotency_key}`; a re-entered fan-out re-runs every item.\n")
    verifies = ""
    if node.verifies:
        verifies = (f"\nThis node verifies `{node.verifies}`. Judge the work adversarially; "
                    "do not rubber-stamp.\n")
    return f"""---
{os.linesep.join(fm)}
---

You are node `{node.name}` of the `{graph.name}` graph (source: `{os.path.basename(graph.path)}`).
Do exactly this node's job — the workflow around you routes the rest.

## State you read
{os.linesep.join(reads)}

## State you write (returned as structured output — the schema is enforced)
{os.linesep.join(writes)}

## Advisory for this target (declared, not enforced by generated code)
{os.linesep.join(advisory)}
{fanout}{verifies}
## Evidence

Your output must carry the evidence for every state field you set (what you did,
what you observed, why the value is what it is). Downstream nodes act on your
words; unsupported claims propagate as bugs.

Trace correlation: spans from this unit carry the label `graphspec:{node.name}`.
"""


# ------------------------------------------------------------- workflow script

def _emit_order(graph: Graph) -> list[str]:
    """Stable emission order: BFS from entry over declared edges, then leftovers."""
    order: list[str] = []
    seen: set[str] = set()
    queue = deque([graph.entry] if graph.entry in graph.nodes else [])
    while queue:
        n = queue.popleft()
        if n in seen:
            continue
        seen.add(n)
        order.append(n)
        for e in graph.edges:
            if e.from_ == n and e.to in graph.nodes and e.to not in seen:
                queue.append(e.to)
    order.extend(sorted(n for n in graph.nodes if n not in seen))
    return order


def _js_str(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _exhaust_target(target: str, indent: str) -> list[str]:
    if target == "fail":
        return [f"{indent}throw new Error('cycle cap exhausted')"]
    if target == "escalate":
        return [f"{indent}return {{ escalated: true, pending: node, state }}  // clearly marked: operator attention required"]
    return [f"{indent}node = {_js_str(target)}; break"]


def _transitions(graph: Graph, name: str, indent: str = "      ") -> list[str]:
    """The if/else chain implementing a node's outgoing declared edges."""
    lines: list[str] = []
    edges = [e for e in graph.edges if e.from_ == name]
    unconditional = [e for e in edges if not e.when]
    for e in edges:
        body: list[str] = []
        inner = indent + ("  " if e.when else "")
        if e.counter:
            body.append(f"{inner}state.{e.counter} += 1")
            if e.max is not None and e.on_exhausted:
                body.append(f"{inner}if (state.{e.counter} > {e.max}) {{  // cap exhausted -> {e.on_exhausted}")
                body.extend(_exhaust_target(e.on_exhausted, inner + "  "))
                body.append(f"{inner}}}")
        body.append(f"{inner}node = {_js_str(e.to)}; break")
        if e.when:
            lines.append(f"{indent}if ({when_to_js(e.when)}) {{")
            lines.extend(body)
            lines.append(f"{indent}}}")
        else:
            lines.extend(body)
    if not unconditional:
        if edges:
            lines.append(f"{indent}node = null; break  // no edge guard matched — run ends here")
        else:
            lines.append(f"{indent}node = null; break  // terminal")
    return lines


def _agent_opts(graph: Graph, node: Node) -> str:
    opts = [f"label: {_js_str('graphspec:' + node.name)}"]
    if node.kind == "subagent" and node.agent:
        opts.append(f"agentType: {_js_str(node.agent)}")
    if node.model:
        opts.append(f"model: {_js_str(node.model)}")
    if node.isolation == "worktree":
        opts.append("isolation: 'worktree'")
    schema = state_schema(graph, node.name)
    if schema is not None:
        opts.append(f"schema: SCHEMAS.{node.name}")
    return "{ " + ", ".join(opts) + " }"


def _node_case(graph: Graph, node: Node) -> list[str]:
    name = node.name
    lines = [f"    case {_js_str(name)}: {{"]
    substrate = graph.effective_substrate(node)
    if name in graph.checkpoints_after:
        lines.append("      // checkpoint after this node (advisory for --target claude)")
    if substrate not in SCAFFOLD_SUBSTRATES:
        lines.append(f"      // substrate '{substrate}' is render-only in graphspec 1 —")
        lines.append("      // implement this node in that substrate; the workflow passes through.")
        lines.extend(_transitions(graph, name))
        lines.append("    }")
        return lines

    if node.kind == "terminal":
        lines.append(f"      log('reached terminal {name}')")
        lines.extend(_transitions(graph, name))
    elif node.kind == "human":
        presents = node.presents or []
        packed = ", ".join(f"{p}: state.{p}" for p in presents)
        lines.append(f"      // human node — timeout {node.timeout} / on_timeout {node.on_timeout} are advisory:")
        lines.append("      // a workflow cannot wait for people. Return with pending state, clearly marked.")
        lines.append(f"      return {{ pending: {_js_str(name)}, presents: {{ {packed} }}, state }}")
    elif node.fan_out_over:
        conc = node.concurrency or 1
        item = node.as_ or "item"
        lines.append(f"      phase({_js_str(name)})")
        lines.append(f"      const items = state.{node.fan_out_over} || []")
        lines.append(f"      results[{_js_str(name)}] = []")
        lines.append(f"      for (let i = 0; i < items.length; i += {conc}) {{  // concurrency: {conc}")
        lines.append(f"        const batch = await parallel(items.slice(i, i + {conc}).map({item} => () =>")
        lines.append(f"          agent(`Run node '{name}' of graph '{graph.name}' for item ${{{item}}}. "
                     f"Idempotency key: {node.idempotency_key or ''}. Completed keys must be cheap no-ops.`,")
        lines.append(f"            {_agent_opts(graph, node)})))")
        lines.append(f"        results[{_js_str(name)}].push(...batch.filter(Boolean))")
        lines.append("      }")
        lines.extend(_transitions(graph, name))
    else:
        lines.append(f"      phase({_js_str(name)})")
        joins = f"\nJoin policy '{node.join}' over ${{JSON.stringify(results)}}." if node.join else ""
        if node.kind == "function":
            prompt = (f"Execute {node.impl or '(impl missing)'} for node '{name}' of graph "
                      f"'{graph.name}' and return its declared state writes.")
        else:
            prompt = f"Run node '{name}' of graph '{graph.name}'."
        if node.verifies:
            prompt += f" Verify the output of '{node.verifies}' adversarially."
        schema = state_schema(graph, node.name)
        out = "const out = " if schema else ""
        lines.append(f"      {out}await agent(`{prompt}{joins}`, {_agent_opts(graph, node)})")
        if schema:
            lines.append("      Object.assign(state, out)")
        lines.extend(_transitions(graph, name))
    lines.append("    }")
    return lines


def workflow_script(graph: Graph) -> str:
    order = _emit_order(graph)
    counters = sorted(graph.counter_fields())
    schemas = {n: state_schema(graph, n) for n in order}
    schemas = {n: s for n, s in schemas.items() if s is not None}

    lines: list[str] = []
    lines.append("// Generated by graphspec scaffold — DO NOT hand-edit the control flow.")
    lines.append(f"// Source of truth: {os.path.basename(graph.path)}. Edit the YAML, re-run scaffold.")
    lines.append("export const meta = {")
    lines.append(f"  name: {_js_str(graph.name)},")
    lines.append(f"  description: {_js_str('Generated from ' + os.path.basename(graph.path) + ' (graphspec 1)')},")
    phase_names = [n for n in order
                   if graph.nodes[n].kind not in ("terminal", "human")
                   and graph.effective_substrate(graph.nodes[n]) in SCAFFOLD_SUBSTRATES]
    lines.append("  phases: [" + ", ".join("{ title: " + _js_str(n) + " }" for n in phase_names) + "],")
    lines.append("}")
    lines.append("")
    lines.append("// Counters are initialized at run start (graphspec semantics); nodes never write them.")
    init = ", ".join(f"{c}: 0" for c in counters)
    lines.append(f"const state = {{ {init} }}")
    lines.append("const results = {}  // per-node fan-out results, consumed by join nodes")
    lines.append("")
    lines.append("// Structured-output schemas derived from each node's declared state writes —")
    lines.append("// the generated mechanism that keeps declaration and implementation in sync.")
    lines.append("const SCHEMAS = {")
    for n in sorted(schemas):
        lines.append(f"  {n}: {json.dumps(schemas[n], sort_keys=True)},")
    lines.append("}")
    lines.append("")
    lines.append(f"let node = {_js_str(graph.entry)}")
    lines.append("while (node) {")
    lines.append("  switch (node) {")
    for n in order:
        lines.extend(_node_case(graph, graph.nodes[n]))
    lines.append("    default: {")
    lines.append("      throw new Error(`unknown node ${node}`)")
    lines.append("    }")
    lines.append("  }")
    lines.append("}")
    lines.append("return { state, results }")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ hooks + IO

def hooks_fragment(graph: Graph) -> str:
    deterministic = [
        {"from": e.from_, "to": e.to} for e in graph.edges if not e.when
    ]
    fragment = {
        "_comment": (
            "Generated by graphspec scaffold. deterministic_edges lists the transitions "
            "with no when guard — they must fire every time their source node completes; "
            "the generated workflow enforces them, and a Stop hook can assert they ran. "
            "The hooks entry keeps the declaration honest: validate on every edit of the "
            "graph file. Merge into .claude/settings.json."
        ),
        "deterministic_edges": deterministic,
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Edit|Write",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"sh -c 'case \"$CLAUDE_FILE_PATHS\" in *{os.path.basename(graph.path)}*) graphspec validate {os.path.basename(graph.path)};; esac'",
                        }
                    ],
                }
            ]
        },
    }
    return json.dumps(fragment, indent=2, sort_keys=True) + "\n"


IMPL_STUB = '''"""Stub generated by graphspec scaffold for node '{node}' (graph '{graph}').

Implement the node here. Its declared contract:
reads: {reads}
writes: {writes}
"""


def main() -> None:
    raise NotImplementedError("generated stub for node '{node}' — implement me")
'''


def run(path: str, out: str = ".", force: bool = False, target: str = "claude") -> int:
    graph = load(path)
    diags = run_rules(graph)
    # Missing impl files are E-KIND errors, but emitting their stubs is one of
    # scaffold's jobs — tolerate exactly those; refuse on anything else.
    blocking = [d for d in diags if d.severity == "error"
                and not (d.rule_id == "E-KIND" and "impl path" in d.message)]
    if blocking:
        for d in blocking:
            print(d.format(), file=sys.stderr)
        print("scaffold refuses to generate from an invalid graph", file=sys.stderr)
        return 1

    render_only = sorted(
        n.name for n in graph.nodes.values()
        if graph.effective_substrate(n) not in SCAFFOLD_SUBSTRATES
    )
    if render_only:
        subs = sorted({graph.effective_substrate(graph.nodes[n]) for n in render_only})
        print(
            f"warning: substrate(s) {', '.join(subs)} are render-only in graphspec 1; "
            f"scaffold emits no code for: {', '.join(render_only)}",
            file=sys.stderr,
        )

    files: list[tuple[str, str]] = []
    for name in sorted(graph.nodes):
        node = graph.nodes[name]
        if node.kind == "subagent" and node.agent:
            files.append((os.path.join(out, ".claude", "agents", f"{node.agent}.md"),
                          agent_md(graph, node)))
    files.append((os.path.join(out, ".claude", "workflows", f"{graph.name}.js"),
                  workflow_script(graph)))
    files.append((os.path.join(out, ".claude", "graphspec", "hooks-fragment.json"),
                  hooks_fragment(graph)))

    yaml_dir = os.path.dirname(os.path.abspath(graph.path))
    for name in sorted(graph.nodes):
        node = graph.nodes[name]
        if node.impl:
            impl_path = os.path.join(yaml_dir, node.impl)
            if not os.path.exists(impl_path):
                files.append((impl_path, IMPL_STUB.format(
                    node=name, graph=graph.name,
                    reads=", ".join(f.name for f, _ in graph.reads_of(name)) or "(none)",
                    writes=", ".join(sorted(graph.writes_of(name))) or "(none)",
                )))

    for fpath, content in files:
        if os.path.exists(fpath) and not force:
            print(f"skip {fpath} (exists; use --force to overwrite)")
            continue
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"write {fpath}")
    return 0
