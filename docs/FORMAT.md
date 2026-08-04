# The graphspec format — reference

This document mirrors appendix A of *Graph Engineering*. The format version key is
`graphspec: 1`. The conformance target is
[`examples/software-delivery.yaml`](../examples/software-delivery.yaml): it must validate
clean under every rule below. A machine-readable schema ships at
[`schema/graphspec.schema.json`](../schema/graphspec.schema.json) so editors can validate
on save.

## Top level

| Key | Meaning |
|---|---|
| `graphspec` | Format version. Always `1`. |
| `name` | Graph name; used by render and scaffold. |
| `entry` | The node every run starts at. Anchored at the top of renderings. |
| `terminals` | Nodes where a run may end. No outgoing edges allowed. |
| `substrate` | Optional graph-wide default substrate (see below). |
| `state` | Declared state fields (the *only* data that flows between nodes). |
| `nodes` | The nodes. |
| `edges` | The edges, in declaration order. |
| `checkpoints` | `after: [node, …]` — advisory checkpoint positions. |

Unknown keys anywhere produce a **warning** (`W-UNKNOWN-KEY`), never an error — the
format stays extensible.

## Nodes

- `kind` ∈ `function | llm | subagent | human | terminal`.
- `substrate` ∈ `subagent | workflow | team | scheduled | channel`, optional, settable per
  node or once for the whole graph. Default: `workflow`. In v1, `scaffold` emits code only
  for `workflow` and `subagent`; the other three are render-only and `scaffold` prints a
  warning naming them.
- `effects` ∈ `none | external`, default `none`. `effects: external` requires an
  `idempotency_key` (`E-EFFECTS`).
- `idempotency_key` is a template string over declared state field names in `{braces}`,
  plus the node's own `as` binding if it has one.
- `impl:` paths resolve **relative to the YAML file's directory** (`E-KIND`).
- `join` ∈ `all | any | majority | first`. Meaningful on nodes with more than one inbound
  edge, or whose predecessor declares `fan_out_over`.
- `kind: human` requires `timeout` and `on_timeout` (`E-HUMAN`).
- A node with `verifies: X` must differ from `X` in `agent` or in `model` (`E-VERIFIER`).

## State

- `state.*.type` ∈ `string | number | bool | list | object | enum | ref`. `enum` requires
  `values`. `ref` means "a pointer to an artifact on disk", not the artifact itself.
- **Reads and optional reads.** `read:` lists the nodes that consume a field. A reader
  suffixed with `?` declares an **optional read**: the node tolerates the field being
  unset, and `E-READ-UNSET` does not apply to it. *YAML note:* inside a flow sequence the
  suffix must be quoted — `read: ['implement?', 'verify?']` — because a bare trailing `?`
  before `,` or `]` is not valid YAML.
- Fields listed in a `human` node's `presents` are treated as optional reads of that node.
- **Writers and their outgoing edges.** A node's own writes are visible to its outgoing
  edges — that is what makes an entry node's guards on its own classification legal
  without a self-read. Self-reads are a warning (`W-SELF-READ`).
- **Counters.** A field named by any edge's `counter:` is written by that edge, not by a
  node: it is initialized to `0` when the run starts and incremented on each traversal.
  Counter fields must not appear in any node's `write:` list (`W-COUNTER-WRITE`). Edge
  writes count as writes for `E-READ-UNSET` and `E-WHEN-UNSET`.

## Fan-out

`fan_out_over` names a `list` state field. `as` names the per-item binding and is
**required** when `fan_out_over` is present; the binding is available in the node's
`idempotency_key` template and nowhere else. Re-entering a fan-out node (via a cycle)
re-runs **all** items — idempotency keys make completed items cheap no-ops. A node with
`fan_out_over` must not declare state writes in v1; results flow through the join node
(`E-FANOUT`). Both restrictions may be lifted in `graphspec: 2`.

## `when` expressions

A deliberately minimal grammar:

- Identifiers denote state fields.
- String and enum literals are single-quoted: `"category == 'feature'"`. Numbers and
  `true`/`false` are bare.
- Operators: `==`, `!=`, `<`, `<=`, `>`, `>=`, `&&`, `||`, `!`, parentheses. Nothing
  else — no arithmetic, no function calls, no indexing. If a condition needs computation,
  it belongs in a `function` node that writes a field.

## Reserved words

`on_timeout` and `on_exhausted` accept `escalate`, `fail`, or the name of any declared
node. `fail` ends the run as failed. `escalate` halts the run and surfaces it to the
operator — for `--target claude` the generated workflow returns with the pending state in
its return value, clearly marked. Node-valued targets are **edges in every sense**: they
count for reachability, terminal-path analysis, and rendering.

## Validation rules

Every finding prints `file:line: [RULE-ID] message` plus a one-line hint. Errors exit 1;
warnings exit 0 (`--strict` promotes them).

| ID | Rule |
|----|------|
| `E-EDGE-ENDS`   | Every edge `from`/`to` names a declared node |
| `E-UNREACHABLE` | Every node is reachable from `entry` (counting `on_timeout`/`on_exhausted` targets as edges) |
| `E-NO-TERMINAL` | Every node has a path to some node listed in `terminals` (same edge set) |
| `E-TERMINAL`    | Every member of `terminals` has no outgoing edges; every `kind: terminal` node appears in `terminals` |
| `E-KIND`        | Every node has a valid `kind`; every `impl` path exists on disk, resolved relative to the YAML file |
| `E-READ-UNSET`  | Every field a node reads — optional reads excluded — is written by some upstream node or edge on *every* path that reaches it |
| `E-WHEN-UNSET`  | Every identifier in a `when` is a state field written upstream (the edge's own `from` node counts as upstream) |
| `E-VERIFIER`    | A node with `verifies: X` differs from X in `agent` or in `model` |
| `E-FANOUT`      | `fan_out_over` names a `list` field, `as` is present, and the downstream join node declares `join` |
| `E-CYCLE-CAP`   | Every cycle contains at least one edge with `max`, `counter` (a `number` field) and `on_exhausted` |
| `E-EFFECTS`     | Every node with `effects: external` has an `idempotency_key` referencing only declared fields and the node's own `as` binding |
| `E-HUMAN`       | Every `kind: human` node has `timeout` and `on_timeout` |
| `E-PARSE`       | The file is YAML, carries `graphspec: 1`, and each element has the structure its kind requires (an unparseable `when` also reports here) |
| `W-UNKNOWN-KEY` | Unknown keys are ignored but named |
| `W-SELF-READ`   | A node reads a field it writes itself |
| `W-COUNTER-WRITE` | A counter field appears in a node's `write:` list |
| `W-ADVISORY`    | With `--target claude`: declared fields the generated code documents but does not enforce |

`E-CYCLE-CAP` is defined over the graph, not over any traversal: removing all capped
edges must leave the graph acyclic.

## Enforced vs. advisory (`--target claude`)

For a given scaffold target, each field is either *enforced* (the generated code
implements it) or *advisory* (documented in the generated node contract, implemented by
the surrounding process).

| Field | `--target claude` |
|---|---|
| edges, `when` guards | **enforced** (workflow control flow) |
| `fan_out_over` / `as` / `concurrency` / `join` | **enforced** (`parallel()` / `pipeline()` composition) |
| `isolation` | **enforced** (worktree option on generated `agent()` calls) |
| `model`, `agent` | **enforced** (generated call options / agent frontmatter) |
| state writes | **enforced** (structured-output schema on the generated call) |
| `timeout` / `on_timeout` on `human` nodes | *advisory* |
| `checkpoints` | *advisory* |
| `budget_tokens` | *advisory* |

`graphspec validate --target claude` prints a `W-ADVISORY` warning for every advisory
field it finds, so the gap between declaration and generated code is visible, never
silent.
