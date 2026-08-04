# graphspec

**A spec for a graph.** Agent systems built on Claude Code have an *implicit* topology:
it is scattered across `.claude/agents/*.md`, the orchestrator's runtime decisions, and a
few hooks. Nobody can see it whole, review it in a pull request, or diff two versions of
it.

`graphspec` makes that topology an explicit, versioned artifact — a `graphspec.yaml`
file — and gives it five things a hand-drawn diagram cannot:

- a **renderer** (`graphspec render`) — Graphviz DOT/SVG/PNG with a stable visual grammar,
- a **validator** (`graphspec validate`) — twelve mechanical rules, including the one that
  catches a node acting on half the story (`E-READ-UNSET`),
- a **semantic differ** (`graphspec diff`) — topology changes reviewable like code changes,
- a **trace overlay** (`graphspec trace`) — real OpenTelemetry executions drawn onto the
  declared graph, drift included,
- a **generator** (`graphspec scaffold`) — agents, workflow skeletons and structured-output
  schemas that keep the declaration and the implementation in sync.

`graphspec` is the companion tool for the book *Graph Engineering* (Spanish and English
editions).

## What graphspec is not

**`graphspec` does not execute graphs.** It declares, draws, checks, diffs and generates.
If you need durable execution — retries, persistence, resumable state machines — you want
[LangGraph](https://github.com/langchain-ai/langgraph) or
[Temporal](https://temporal.io/); `graphspec` will happily *describe* the graph you run
there. No orchestration runtime, no scheduler, no cloud service, no telemetry, no account.

## Install

```sh
pip install graphspec
```

Python 3.11+. The core depends only on `pyyaml`. `render`, `validate` and `diff` work
without Graphviz installed (DOT output is text); `--format svg|png` needs the `dot`
binary ([graphviz.org/download](https://graphviz.org/download/)).

## Quick start

```sh
graphspec validate examples/software-delivery.yaml
graphspec render examples/software-delivery.yaml > graph.dot
```

The format is one YAML file with `graphspec: 1` at the top. The full reference lives in
[`docs/FORMAT.md`](docs/FORMAT.md); the shipped
[`examples/software-delivery.yaml`](examples/software-delivery.yaml) is the conformance
target and the example printed in the book.

## Validate

```sh
graphspec validate [FILE] [--strict] [--target claude]
```

Each violation prints `file:line: [RULE-ID] message` plus a one-line hint. Exit 1 on any
error, 0 with warnings only; `--strict` promotes warnings to errors. `--target claude`
additionally warns about *advisory* fields — declared behavior the generated code
documents but does not enforce — so the gap between declaration and implementation is
visible, never silent. The rule table is in [`docs/FORMAT.md`](docs/FORMAT.md).

## Render

```sh
graphspec render [FILE] [--format dot|svg|png]
```

Emits Graphviz DOT on stdout by default — deterministic, byte-identical across runs, so
it diffs cleanly in CI. `--format svg|png` shells out to `dot` and fails with an install
hint when Graphviz is absent. The visual grammar is stable (the book prints these
figures): node shape and colour by `kind` (`function` rectangle, `llm` rounded box,
`subagent` double border, `human` diamond, `terminal` doubled circle); conditional edges
dashed and labelled with their `when`; cycle-capping and `on_timeout`/`on_exhausted`
edges in a distinct colour with `max=N`; shape-encoded badges (⚡ external effects,
⧉`∥N` fan-out with concurrency, `∀ ∃ ½ 1` join glyphs, ✓ checkpoints); substrate
clusters when a graph spans more than one substrate; `entry` at the top, `terminals` at
the bottom.

## Trace

```sh
graphspec trace [FILE] --otlp FILE_OR_ENDPOINT [--session SESSION_ID]
```

Overlays real executions on the declared graph using the OpenTelemetry spans Claude Code
already emits (`CLAUDE_CODE_ENABLE_TELEMETRY=1` plus
`CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`) — no invented log format. Accepts an OTLP JSON
export or a collector endpoint. The output is DOT where executed nodes are filled in
proportion to token cost (with a numeric badge — never tint alone), un-executed nodes
are greyed out, repeat visits are labelled `×N` and the node where the run stopped is
highlighted; a per-node cost table follows as `//` DOT comments, so the whole stream
still pipes into `dot`.

Spans map onto nodes by the correlation contract `scaffold` emits: a
`graphspec:<node>` label first, the `agent` name second. Every executed unit that
matches neither is reported as **drift** between the declared topology and the real
one — surfacing that is a feature, not an error. Span shapes are beta; every assumption
about them lives in one fixture-covered module (`graphspec/trace/mapping.py`).

## Diff

```sh
graphspec diff OLD NEW [--format text|markdown]
```

Semantic diff of two graph files: nodes, edges and state fields added, removed and
changed (kind, agent, model, guards, caps, joins, effects). Exit 0 when topologically
identical, 1 otherwise; `--format markdown` emits a PR-comment-ready summary. This — not
a rendered image — is what makes topology reviewable: a change in the graph gets
reviewed the way a change in code does.

## Scaffold

```sh
graphspec scaffold [FILE] [--out .] [--force] [--target claude]
```

Generates, never overwriting by default: `.claude/agents/<agent>.md` per subagent node
(frontmatter plus the node's contract — reads with optional markers, writes, advisory
fields, expected evidence); a dynamic workflow skeleton under `.claude/workflows/` whose
control flow is derived from the edges, guards, caps, fan-out and join policies; a
**structured-output schema per writing node**, derived from the declared state fields and
injected into the generated `agent()` call — the mechanism that keeps declaration and
implementation in sync; `graphspec:<node>` correlation labels on every generated unit
(what `trace` maps spans by); a hooks fragment for deterministic edges; and stubs for
missing `impl:` paths. Re-running is idempotent. `validate --target claude` names every
advisory field so the declaration/generated-code gap is never silent.

## CI: review topology like code

`.github/workflows/graphspec-validate.yml` is a **reusable workflow**: call it from any
repository to validate `graphspec.yaml` on every pull request, post the `graphspec diff`
against the base branch as a PR comment, and upload the rendered diagram as an artifact.

```yaml
jobs:
  graphspec:
    uses: librosdeia/graphspec/.github/workflows/graphspec-validate.yml@main
    with:
      file: ./graphspec.yaml
```

## Serve — the editor

```sh
graphspec serve [FILE] [--port PORT]
```

A local editor at `http://localhost:PORT`: YAML on the left, live graph on the right,
validation inline as you type — with the exact CLI error strings, so the terminal, CI
and the editor all speak identically. **One renderer:** the browser shows SVG produced
server-side by the same pipeline as `graphspec render`; the editor is a view, never a
second layout implementation. Without Graphviz it degrades honestly: DOT preview plus
fully live validation.

Three interactions you won't find in a generic YAML editor:

1. **Bidirectional linking** — click a node to jump to its YAML; move the cursor to
   halo the element in the canvas; hover an edge for its `when`/`max`/`counter`.
2. **The data-flow lens** — select any state field: writers, readers and optional
   readers get distinct outlines, and every path along which a required reader would
   receive the field *unwritten* is tinted red — `E-READ-UNSET`, made visible before
   any model runs.
3. **Trace overlay** — drop an OTLP JSON export on the canvas: cost-proportional fills,
   `×N` repeat badges, the stopped node highlighted, a per-node cost table, drift
   surfaced.

Local-first by design: binds to `127.0.0.1` only, every asset vendored, zero external
requests, no telemetry. Works on a plane.

## Status

**v1.0.0.** The `v1.0-book` tag freezes the state the first edition of *Graph
Engineering* describes; the format version is `graphspec: 1`. Built milestone by
milestone: `v0.1.0` model + validator, `v0.2.0` render, `v0.3.0` trace, `v0.4.0`
scaffold + diff + CI, `v1.0.0` the serve editor.

## License

MIT.
