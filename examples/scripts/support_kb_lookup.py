"""Stub referenced by support-triage.yaml's `kb_lookup` node.

A real implementation searches the knowledge base for the ticket's topic and
writes the `candidate_answer` / `candidate_confidence` state fields.
graphspec never executes this file — `E-KIND` only checks that declared
`impl:` paths exist next to the YAML.
"""


def kb_lookup(ticket_id: str) -> tuple[str, float]:
    raise NotImplementedError("example stub — replace with your own KB search")
