"""Stub referenced by support-triage.yaml's `resolve_ticket` node.

A real implementation records the agent's (or tier-2 specialist's)
resolution and marks the ticket resolved in the ticketing system; it must
be idempotent under its declared `idempotency_key`. graphspec never
executes this file — `E-KIND` only checks that declared `impl:` paths
exist next to the YAML.
"""


def resolve_ticket(ticket_id: str, resolution_notes: str) -> None:
    raise NotImplementedError("example stub — replace with your own resolution logic")
