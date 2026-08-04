"""Stub referenced by support-triage.yaml's `send_reply` node.

A real implementation sends `final_response` to the customer over the
support channel; it must be idempotent under its declared `idempotency_key`.
graphspec never executes this file — `E-KIND` only checks that declared
`impl:` paths exist next to the YAML.
"""


def send_reply(ticket_id: str, final_response: str) -> None:
    raise NotImplementedError("example stub — replace with your own reply-sending logic")
