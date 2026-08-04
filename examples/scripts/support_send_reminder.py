"""Stub referenced by support-triage.yaml's `send_reminder` node.

A real implementation pings the assigned agent that a ticket is still
waiting on them; it must be idempotent under its declared `idempotency_key`
(keyed on the reminder count so repeat reminders are distinct, safe sends).
graphspec never executes this file — `E-KIND` only checks that declared
`impl:` paths exist next to the YAML.
"""


def send_reminder(ticket_id: str, reminder_count: int) -> None:
    raise NotImplementedError("example stub — replace with your own reminder logic")
