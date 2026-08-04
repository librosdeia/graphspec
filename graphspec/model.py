"""The graphspec object model.

One shared model backs every command: ``validate``, ``render``, ``diff``,
``trace``, ``scaffold`` and ``serve`` all consume the classes below. The parser
(:mod:`graphspec.parser`) is the only producer.

Reserved-word targets for ``on_timeout`` / ``on_exhausted`` that name a declared
node are **edges in every sense** (reachability, terminal paths, rendering); the
model materializes them as synthetic :class:`Edge` objects available through
:meth:`Graph.all_edges`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from graphspec.diagnostics import Diagnostic

KINDS = {"function", "llm", "subagent", "human", "terminal"}
SUBSTRATES = {"subagent", "workflow", "team", "scheduled", "channel"}
STATE_TYPES = {"string", "number", "bool", "list", "object", "enum", "ref"}
JOINS = {"all", "any", "majority", "first"}
EFFECTS = {"none", "external"}
RESERVED_TARGETS = {"escalate", "fail"}

DEFAULT_SUBSTRATE = "workflow"


@dataclass(frozen=True)
class Read:
    node: str
    optional: bool = False


def parse_read(entry: str) -> Read:
    """``"verify?"`` -> optional read by ``verify``; ``"verify"`` -> required."""
    if entry.endswith("?"):
        return Read(entry[:-1], optional=True)
    return Read(entry)


@dataclass
class StateField:
    name: str
    type: str
    line: int = 0
    values: list[str] | None = None
    write: list[str] = field(default_factory=list)
    read: list[Read] = field(default_factory=list)


@dataclass
class Node:
    name: str
    kind: str
    line: int = 0
    raw: dict = field(default_factory=dict)
    agent: str | None = None
    model: str | None = None
    tools: list[str] | None = None
    substrate: str | None = None
    fan_out_over: str | None = None
    as_: str | None = None
    concurrency: int | None = None
    isolation: str | None = None
    effects: str = "none"
    idempotency_key: str | None = None
    verifies: str | None = None
    join: str | None = None
    timeout: str | None = None
    on_timeout: str | None = None
    presents: list[str] | None = None
    impl: str | None = None
    budget_tokens: int | None = None


@dataclass
class Edge:
    from_: str
    to: str
    line: int = 0
    when: str | None = None
    max: int | None = None
    counter: str | None = None
    on_exhausted: str | None = None
    # None for declared edges; "on_timeout" / "on_exhausted" for synthetic ones.
    synthetic: str | None = None

    @property
    def capped(self) -> bool:
        """A cycle-capping edge per E-CYCLE-CAP: max + counter + on_exhausted."""
        return self.max is not None and self.counter is not None and self.on_exhausted is not None


@dataclass
class Graph:
    path: str
    name: str = ""
    entry: str = ""
    terminals: list[str] = field(default_factory=list)
    substrate: str | None = None
    state: dict[str, StateField] = field(default_factory=dict)
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    checkpoints_after: list[str] = field(default_factory=list)
    parse_diagnostics: list[Diagnostic] = field(default_factory=list)

    def synthetic_edges(self) -> list[Edge]:
        """Edges implied by node-valued on_timeout / on_exhausted targets."""
        result: list[Edge] = []
        for node in self.nodes.values():
            target = node.on_timeout
            if target and target not in RESERVED_TARGETS:
                result.append(Edge(from_=node.name, to=target, line=node.line, synthetic="on_timeout"))
        for edge in self.edges:
            target = edge.on_exhausted
            if target and target not in RESERVED_TARGETS:
                result.append(Edge(from_=edge.from_, to=target, line=edge.line, synthetic="on_exhausted"))
        return result

    def all_edges(self) -> list[Edge]:
        return list(self.edges) + self.synthetic_edges()

    def out_edges(self, node: str) -> list[Edge]:
        return [e for e in self.all_edges() if e.from_ == node]

    def in_edges(self, node: str) -> list[Edge]:
        return [e for e in self.all_edges() if e.to == node]

    def edge_writes(self, edge: Edge) -> set[str]:
        """Fields written by traversing this edge (its counter, if any)."""
        return {edge.counter} if edge.counter else set()

    def counter_fields(self) -> set[str]:
        """Fields named as a counter by any declared edge (initialized at run start)."""
        return {e.counter for e in self.edges if e.counter}

    def writes_of(self, node: str) -> set[str]:
        return {f.name for f in self.state.values() if node in f.write}

    def reads_of(self, node: str) -> list[tuple[StateField, Read]]:
        """All declared reads by *node*, with their optionality.

        Fields listed in a human node's ``presents`` are optional reads.
        """
        n = self.nodes.get(node)
        presents = set(n.presents or []) if n is not None else set()
        result: list[tuple[StateField, Read]] = []
        for f in self.state.values():
            for r in f.read:
                if r.node == node:
                    if f.name in presents and not r.optional:
                        r = Read(node, optional=True)
                    result.append((f, r))
        declared = {f.name for f, _ in result}
        for name in presents:
            f = self.state.get(name)
            if f is not None and f.name not in declared:
                result.append((f, Read(node, optional=True)))
        return result

    def effective_substrate(self, node: Node) -> str:
        return node.substrate or self.substrate or DEFAULT_SUBSTRATE
