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

## Status

Pre-1.0, built milestone by milestone (`v0.1.0` = model + validator). The
`v1.0-book` tag will freeze the state the first edition of the book describes.

## License

MIT.
