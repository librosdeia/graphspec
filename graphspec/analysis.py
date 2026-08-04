"""Graph analyses shared by the validation rules, the data-flow lens and trace.

Everything here counts synthetic ``on_timeout`` / ``on_exhausted`` edges as real
edges, per the PRD ("edges in every sense").
"""

from __future__ import annotations

from collections import deque

from graphspec.model import Edge, Graph


def reachable(graph: Graph) -> set[str]:
    """Nodes reachable from ``entry`` over all edges."""
    seen: set[str] = set()
    queue = deque([graph.entry] if graph.entry in graph.nodes else [])
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        for e in graph.out_edges(node):
            if e.to in graph.nodes and e.to not in seen:
                queue.append(e.to)
    return seen


def nodes_reaching_terminals(graph: Graph) -> set[str]:
    """Nodes with a path to some member of ``terminals`` (terminals included)."""
    inbound: dict[str, list[Edge]] = {}
    for e in graph.all_edges():
        inbound.setdefault(e.to, []).append(e)
    seen: set[str] = set()
    queue = deque(t for t in graph.terminals if t in graph.nodes)
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        for e in inbound.get(node, []):
            if e.from_ in graph.nodes and e.from_ not in seen:
                queue.append(e.from_)
    return seen


def uncapped_cycle(graph: Graph) -> list[str] | None:
    """A cycle containing no capped edge, as a node list — or None.

    E-CYCLE-CAP is defined over the graph, not any traversal: removing all
    capped edges must leave the graph acyclic. If it does not, the offending
    cycle found here contains no capped edge by construction.
    """
    adjacency: dict[str, list[str]] = {}
    for e in graph.all_edges():
        if e.capped:
            continue
        if e.from_ in graph.nodes and e.to in graph.nodes:
            adjacency.setdefault(e.from_, []).append(e.to)

    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph.nodes}
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = GREY
        stack.append(node)
        for nxt in adjacency.get(node, []):
            if color[nxt] == GREY:
                return stack[stack.index(nxt):] + [nxt]
            if color[nxt] == WHITE:
                found = dfs(nxt)
                if found:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for start in sorted(graph.nodes):
        if color[start] == WHITE:
            found = dfs(start)
            if found:
                return found
    return None


def _flow(graph: Graph) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Forward must-analysis fixpoint over reachable nodes.

    Returns ``(before, after)``: fields guaranteed written before a node runs,
    and after it runs, on **every** path from entry. Counter fields are always
    available — the PRD initializes them to 0 at run start.
    """
    live = reachable(graph)
    counters = graph.counter_fields()
    all_fields = set(graph.state)
    before = {n: (counters if n == graph.entry else set(all_fields)) for n in live}
    after: dict[str, set[str]] = {}
    inbound: dict[str, list[Edge]] = {}
    for e in graph.all_edges():
        if e.from_ in live and e.to in live:
            inbound.setdefault(e.to, []).append(e)

    changed = True
    while changed:
        changed = False
        for n in live:
            after[n] = before[n] | graph.writes_of(n)
        for n in live:
            if n == graph.entry:
                continue
            sets = [after[e.from_] | graph.edge_writes(e) for e in inbound.get(n, [])]
            new = set.intersection(*sets) if sets else counters.copy()
            if new != before[n]:
                before[n] = new
                changed = True
    for n in live:
        after[n] = before[n] | graph.writes_of(n)
    return before, after


def available_before(graph: Graph) -> dict[str, set[str]]:
    """Per reachable node: fields written on every path that reaches it."""
    return _flow(graph)[0]


def available_after(graph: Graph) -> dict[str, set[str]]:
    """Per reachable node: fields guaranteed written once the node has run
    (its own writes included) — what its outgoing edges may test."""
    return _flow(graph)[1]


def witness_unset_path(graph: Graph, target: str, field: str) -> list[str]:
    """A concrete entry→target path along which *field* is never written.

    Used verbatim in E-READ-UNSET messages. Returns [] if no such path exists
    (or target is unreachable). Counter fields are written at run start, so no
    witness path exists for them.
    """
    if field in graph.counter_fields():
        return []
    # BFS over (node, field_written_after_leaving_node)
    start_written = field in graph.writes_of(graph.entry)
    start = (graph.entry, start_written)
    if graph.entry not in graph.nodes:
        return []
    if graph.entry == target and not start_written:
        return [graph.entry]
    parents: dict[tuple[str, bool], tuple[tuple[str, bool], None] | None] = {start: None}
    queue = deque([start])
    while queue:
        state = queue.popleft()
        node, written = state
        for e in graph.out_edges(node):
            if e.to not in graph.nodes:
                continue
            arrives_written = written or field in graph.edge_writes(e)
            if e.to == target and not arrives_written:
                # reconstruct
                path = [e.to]
                cur: tuple[str, bool] | None = state
                while cur is not None:
                    path.append(cur[0])
                    parent = parents[cur]
                    cur = parent[0] if parent else None
                return list(reversed(path))
            next_state = (e.to, arrives_written or field in graph.writes_of(e.to))
            if next_state not in parents:
                parents[next_state] = (state, None)
                queue.append(next_state)
    return []
