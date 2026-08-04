"""Span → node correlation. The ONE module that knows OTLP and span shapes.

Claude Code's OTel span names and attributes are beta and may change between
releases; every assumption about them lives here, behind module constants, and
is covered by the fixture in tests/fixtures/. Nothing else in graphspec parses
a span.

Correlation contract (shared with scaffold, defined in the PRD):
1. Generated units carry a label of the form ``graphspec:<node>`` — matched
   first, against ANY string attribute value, so attribute-name drift cannot
   break it.
2. Spans are matched by ``agent`` name second (runs of hand-written
   orchestration).
3. Every executed unit that matches neither is reported as drift — a feature,
   not an error.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from graphspec.model import Graph

# ---- beta span-shape assumptions, all in one place -------------------------
SPAN_INTERACTION = "claude_code.interaction"
SPAN_LLM_REQUEST = "claude_code.llm_request"
SPAN_TOOL = "claude_code.tool"
SPAN_HOOK = "claude_code.hook"

MARKER_PREFIX = "graphspec:"
SESSION_KEYS = ("session.id",)
AGENT_KEYS = ("agent.name", "claude_code.agent", "subagent.name", "agent_type")
MODEL_KEYS = ("gen_ai.request.model", "model")
INPUT_TOKEN_KEYS = ("gen_ai.usage.input_tokens", "claude_code.tokens.input", "input_tokens")
OUTPUT_TOKEN_KEYS = ("gen_ai.usage.output_tokens", "claude_code.tokens.output", "output_tokens")
# ----------------------------------------------------------------------------


@dataclass
class Span:
    span_id: str
    parent_id: str | None
    name: str
    start_ns: int
    end_ns: int
    attributes: dict[str, object] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        return (self.end_ns - self.start_ns) / 1e6

    def attr_any(self, keys: tuple[str, ...]):
        for k in keys:
            if k in self.attributes:
                return self.attributes[k]
        return None

    @property
    def session_id(self) -> str | None:
        v = self.attr_any(SESSION_KEYS)
        return str(v) if v is not None else None

    @property
    def marker(self) -> str | None:
        """The graphspec:<node> label, wherever it hides among the attributes."""
        for v in self.attributes.values():
            if isinstance(v, str) and v.startswith(MARKER_PREFIX):
                return v[len(MARKER_PREFIX):]
        return None

    @property
    def agent_name(self) -> str | None:
        v = self.attr_any(AGENT_KEYS)
        return str(v) if v is not None else None


def _attr_value(value: dict):
    """Decode one OTLP AnyValue."""
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        return int(value["intValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "boolValue" in value:
        return bool(value["boolValue"])
    if "arrayValue" in value:
        return [_attr_value(v) for v in value["arrayValue"].get("values", [])]
    return None


def parse_otlp(data: dict) -> list[Span]:
    """Flatten an OTLP/JSON export (resourceSpans→scopeSpans→spans) into Spans.

    Resource attributes (team, tenant, session) are folded into each span's
    attribute dict without overriding the span's own keys.
    """
    spans: list[Span] = []
    for rs in data.get("resourceSpans", []):
        resource_attrs = {
            a["key"]: _attr_value(a.get("value", {}))
            for a in rs.get("resource", {}).get("attributes", [])
        }
        for ss in rs.get("scopeSpans", []):
            for raw in ss.get("spans", []):
                attrs = dict(resource_attrs)
                attrs.update({
                    a["key"]: _attr_value(a.get("value", {}))
                    for a in raw.get("attributes", [])
                })
                spans.append(Span(
                    span_id=raw.get("spanId", ""),
                    parent_id=raw.get("parentSpanId") or None,
                    name=raw.get("name", ""),
                    start_ns=int(raw.get("startTimeUnixNano", 0)),
                    end_ns=int(raw.get("endTimeUnixNano", 0)),
                    attributes=attrs,
                ))
    return spans


@dataclass
class Correlation:
    """What actually ran, mapped onto the declared graph."""
    visits: dict[str, int] = field(default_factory=dict)          # node -> times entered
    tokens: dict[str, int] = field(default_factory=dict)          # node -> total tokens
    latency_ms: dict[str, float] = field(default_factory=dict)    # node -> total wall ms
    stopped_at: str | None = None                                 # last node to finish
    drift: list[str] = field(default_factory=list)                # executed-but-undeclared
    unexecuted: list[str] = field(default_factory=list)           # declared-but-not-run

    def max_tokens(self) -> int:
        return max(self.tokens.values(), default=0)


def _span_tokens(span: Span) -> int:
    tin = span.attr_any(INPUT_TOKEN_KEYS) or 0
    tout = span.attr_any(OUTPUT_TOKEN_KEYS) or 0
    try:
        return int(tin) + int(tout)
    except (TypeError, ValueError):
        return 0


def correlate(graph: Graph, spans: list[Span], session: str | None = None) -> Correlation:
    if session:
        spans = [s for s in spans if s.session_id in (None, session)]
    children: dict[str | None, list[Span]] = {}
    for s in spans:
        children.setdefault(s.parent_id, []).append(s)

    def unit_of(span: Span) -> tuple[str | None, str | None]:
        """(declared node, drift description) for a span, else (None, None)."""
        marker = span.marker
        if marker is not None:
            if marker in graph.nodes:
                return marker, None
            return None, f"unit labelled '{MARKER_PREFIX}{marker}' matches no declared node"
        agent = span.agent_name
        if agent is not None:
            for node in graph.nodes.values():
                if node.agent == agent:
                    return node.name, None
            return None, f"executed agent '{agent}' matches no declared node"
        return None, None

    corr = Correlation()
    mapped_ids: set[str] = set()
    units: list[tuple[Span, str]] = []
    for s in spans:
        node, drift = unit_of(s)
        if node is not None:
            units.append((s, node))
            mapped_ids.add(s.span_id)
        elif drift is not None and drift not in corr.drift:
            corr.drift.append(drift)

    def descendant_tokens(span: Span) -> int:
        """LLM tokens under *span*, not crossing into a nested mapped unit."""
        total = _span_tokens(span) if span.name == SPAN_LLM_REQUEST else 0
        for child in children.get(span.span_id, []):
            if child.span_id in mapped_ids:
                continue
            total += descendant_tokens(child)
        return total

    last_end = -1
    for span, node in units:
        corr.visits[node] = corr.visits.get(node, 0) + 1
        corr.tokens[node] = corr.tokens.get(node, 0) + descendant_tokens(span)
        corr.latency_ms[node] = corr.latency_ms.get(node, 0.0) + span.duration_ms
        if span.end_ns > last_end:
            last_end = span.end_ns
            corr.stopped_at = node

    corr.unexecuted = sorted(n for n in graph.nodes if n not in corr.visits)
    return corr
