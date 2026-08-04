"""Stub referenced by support-triage.yaml's `auto_close` node.

A real implementation closes a ticket that exhausted its reminder budget
without an agent response, recording `closure_reason`; it must be
idempotent under its declared `idempotency_key`. graphspec never executes
this file — `E-KIND` only checks that declared `impl:` paths exist next to
the YAML.
"""


def auto_close(ticket_id: str) -> str:
    raise NotImplementedError("example stub — replace with your own auto-close logic")
